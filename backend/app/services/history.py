"""Read-only provider calls, atomic batch checkpoints and silent historical ingestion.

Never follow provider paging URLs: store only opaque cursors, keeping tokens off disk
and away from browser responses. Each worker transaction holds a row lock, so a
crash rolls back both messages and checkpoint; another worker can resume safely.
"""

import hashlib
from datetime import datetime, timedelta, timezone

from flask import current_app

from ..common import APIError
from ..extensions import db
from ..models import HistorySync, WhatsAppConnection, Workspace, now
from ..utils.whatsapp_message import normalize_raw_message
from . import instagram, whatsapp
from .evolution import EvolutionService
from .instagram import client as instagram_client

BATCH_SIZE = 200


def source(channel, workspace_id, connection_id=None):
    if channel == 'instagram':
        row = instagram.active_connection(workspace_id, connection_id)
        return row, row.instagram_id
    row = WhatsAppConnection.query.filter_by(workspace_id=workspace_id).first()
    if not row:
        raise APIError('Configure o WhatsApp desta conta.', 409)
    return row, row.instance_name


def next_cursor(body, previous=None):
    paging = body.get('paging') or {}
    if not paging.get('next'):
        return None
    after = (paging.get('cursors') or {}).get('after')
    if not isinstance(after, str) or not after or after == previous:
        raise APIError('O provedor não avançou a paginação. Retome mais tarde.', 502)
    return after


def messages_page(connection, page):
    body = EvolutionService(connection).request(
        'POST',
        '/chat/findMessages/' + connection.instance_name,
        {'where': {}, 'page': page, 'offset': BATCH_SIZE, 'limit': BATCH_SIZE},
    )
    envelope = body.get('messages', body) if isinstance(body, dict) else body
    rows = envelope.get('records', []) if isinstance(envelope, dict) else envelope
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise APIError('Formato de histórico do WhatsApp inválido.', 502)
    total = envelope.get('total', 0) if isinstance(envelope, dict) else 0
    return rows, int(total or 0)


def remember_mapping(mappings, raw):
    key = raw.get('key') or {}
    jid, alternate = key.get('remoteJid', ''), key.get('remoteJidAlt') or raw.get('remoteJidAlt') or ''
    if jid.endswith('@s.whatsapp.net') and alternate.endswith('@lid'):
        jid, alternate = alternate, jid
    if jid.endswith('@lid') and alternate.endswith('@s.whatsapp.net'):
        # Conflicting identities must never merge two people. None permanently quarantines the mapping.
        if jid not in mappings:
            mappings[jid] = alternate
        elif mappings[jid] != alternate:
            mappings[jid] = None


def whatsapp_step(job, connection):
    cursor = dict(job.cursor)
    page = cursor.get('page', 1)
    mappings = dict(cursor.get('mappings', {}))
    rows, total = messages_page(connection, page)
    job.total = total
    fingerprint = hashlib.sha256('|'.join(str((r.get('key') or {}).get('id')) for r in rows).encode()).hexdigest()
    if rows and fingerprint == cursor.get('fingerprint'):
        raise APIError('A Evolution repetiu a página. Retome após verificar o provedor.', 502)
    if job.phase == 'mapping':
        for raw in rows:
            remember_mapping(mappings, raw)
    else:
        for raw in rows:
            job.scanned += 1
            key = raw.get('key') or {}
            jid = key.get('remoteJid', '')
            if jid.endswith('@lid'):
                target = mappings.get(jid)
                if not target:
                    job.unresolved += 1
                    job.skipped += 1
                    continue
                raw = {**raw, 'key': {**key, 'remoteJidAlt': target}}
            normalized = normalize_raw_message(raw)
            if not normalized or not normalized.get('evolution_id'):
                job.skipped += 1
                continue
            # Live ingestion tolerates absent timestamps; historical ingestion must never invent one.
            try:
                value = raw['messageTimestamp']
                seconds = int(value['low'] if isinstance(value, dict) else value)
                occurred = datetime.fromtimestamp(seconds, timezone.utc)
                if occurred > now() + timedelta(minutes=5):
                    raise ValueError()
            except (KeyError, TypeError, ValueError, OSError, OverflowError):
                job.skipped += 1
                continue
            _, added = whatsapp.ingest(connection, raw, historical=True)
            if added:
                job.imported += 1
            else:
                job.duplicates += 1
    # Use an empty page as the end marker: provider totals and short pages can change.
    if not rows:
        if job.phase == 'mapping':
            job.phase = 'messages'
            job.cursor = {
                'run_id': cursor.get('run_id'),
                'page': 1,
                'mappings': mappings,
                'mapped_records': cursor.get('mapped_records', 0),
            }
        else:
            job.status = 'completed'
    else:
        job.cursor = {
            **cursor,
            'page': page + 1,
            'mappings': mappings,
            'fingerprint': fingerprint,
            'mapped_records': cursor.get('mapped_records', 0) + (len(rows) if job.phase == 'mapping' else 0),
        }


def graph_records(body):
    if not isinstance(body, dict) or not isinstance(body.get('data'), list):
        raise APIError('Formato de histórico do Instagram inválido.', 502)
    if any(not isinstance(row, dict) for row in body['data']):
        raise APIError('Registro de histórico do Instagram inválido.', 502)
    return body['data']


def instagram_step(job, connection):
    token = instagram.cipher().decrypt(connection.encrypted_token.encode()).decode()
    cursor = dict(job.cursor)
    pending = list(cursor.get('pending', []))
    if not pending:
        if cursor.get('listed') and not cursor.get('after'):
            job.status = 'completed'
            return
        params = {'platform': 'instagram', 'fields': 'id', 'limit': 30}
        if cursor.get('after'):
            params['after'] = cursor['after']
        body = instagram_client.graph(connection.instagram_id + '/conversations', token, params=params)
        pending = [r['id'] for r in graph_records(body) if r.get('id')]
        after = next_cursor(body, cursor.get('after'))
        job.total += len(pending)
        job.phase = 'conversations'
        job.cursor = {**cursor, 'pending': pending, 'after': after, 'listed': True}
        return
    params = {'fields': 'id,created_time,from,to,message,attachments', 'limit': 100}
    if cursor.get('message_after'):
        params['after'] = cursor['message_after']
    body = instagram_client.graph(pending[0] + '/messages', token, params=params)
    for raw in graph_records(body):
        job.scanned += 1
        sender = str((raw.get('from') or {}).get('id', ''))
        recipients = (raw.get('to') or {}).get('data', [])
        recipient = next((str(r.get('id')) for r in recipients if str(r.get('id')) != sender), '')
        # Validate participation before constructing the webhook-shaped historical record.
        if connection.instagram_id not in (sender, recipient) or not raw.get('id'):
            job.skipped += 1
            continue
        try:
            occurred = datetime.fromisoformat(raw['created_time'].replace('Z', '+00:00'))
            if occurred.tzinfo is None or occurred > now() + timedelta(minutes=5):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            job.skipped += 1
            continue
        item = {
            'sender': {'id': sender},
            'recipient': {'id': recipient},
            'timestamp': int(occurred.timestamp() * 1000),
            'message': {'mid': raw['id'], 'text': raw.get('message'), 'attachments': raw.get('attachments')},
        }
        key = hashlib.sha256((connection.id + ':' + raw['id']).encode()).hexdigest()
        if instagram.ingest_message(connection, item, key, historical=True):
            job.imported += 1
        else:
            job.duplicates += 1
    after = next_cursor(body, cursor.get('message_after'))
    if not after:
        pending.pop(0)
    job.phase = 'messages'
    job.cursor = {**cursor, 'pending': pending, 'message_after': after}


def process(limit=2):
    """One bounded batch per active job, also safe with multiple PostgreSQL workers."""
    ids = [
        r.id
        for r in HistorySync.query.filter(HistorySync.status.in_(('queued', 'running')))
        .order_by(HistorySync.updated_at)
        .limit(limit)
        .all()
    ]
    processed = 0
    db.session.rollback()
    for identifier in ids:
        job = HistorySync.query.filter_by(id=identifier).with_for_update(skip_locked=True).first()
        if not job or job.status not in ('queued', 'running'):
            db.session.rollback()
            continue
        checkpoint = job.cursor
        try:
            workspace = db.session.get(Workspace, job.workspace_id)
            if not workspace or not workspace.active:
                raise APIError('A conta foi desativada.', 409)
            connection, identity = source(
                job.channel, job.workspace_id, job.connection_id if job.channel == 'instagram' else None
            )
            if connection.id != job.connection_id or identity != job.identity:
                raise APIError('A conexão mudou. Inicie uma nova sincronização.', 409)
            job.status = 'running'
            if job.channel == 'whatsapp':
                whatsapp_step(job, connection)
            else:
                instagram_step(job, connection)
            db.session.commit()
        except Exception as error:
            db.session.rollback()
            job = HistorySync.query.filter_by(id=identifier).with_for_update().one()
            if job.status in ('queued', 'running') and job.cursor == checkpoint:
                job.status = 'failed'
                job.error = (
                    error.message
                    if isinstance(error, APIError)
                    else 'Falha na importação. Retome ou confira o servidor.'
                )
                db.session.commit()
            current_app.logger.warning('history_sync_failed job=%s type=%s', identifier, type(error).__name__)
        processed += 1
    return processed
