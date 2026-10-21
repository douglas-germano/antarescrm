from datetime import timedelta, datetime, timezone
from pathlib import Path
import json
from flask import current_app
from flask import Blueprint, g
from sqlalchemy import func
from marshmallow import fields as f, validate
from ..extensions import db
from ..models import WorkerHeartbeat, AutomationJob, InboxMessage, CommunicationSuppression, Contact, InboxThread, now
from ..common import require, query, payload, get, add, commit, page, APIError, audit
from ..schemas import StrictSchema, choice, ref, text
from ..services.communications import account_config, available

bp = Blueprint('operations', __name__)


class SuppressionSchema(StrictSchema):
    contact_id = ref(required=True)
    channel = choice('email sms whatsapp', required=True)
    reason = text(100)


@bp.get('/operations/status')
@require('owner', 'admin')
def status():
    heartbeat = WorkerHeartbeat.query.filter_by(name='default').first()
    counts = lambda model, column: {key: count for key, count in query(model).with_entities(column, func.count()).group_by(column).all()}
    channels = []
    for channel, required in [('email', ['host', 'from_address']), ('sms', ['account_sid', 'auth_token', 'from_number']), ('whatsapp', [])]:
        config = account_config(g.workspace_id, channel)
        channels.append({'channel': channel, 'configured': available(g.workspace_id, channel),
            'missing': [key for key in required if not config.get(key)]})
    backup = None
    try:
        record = json.loads(Path(current_app.config['BACKUP_STATUS_PATH']).read_text())
        created = datetime.fromisoformat(record['created_at'])
        backup = {'last_backup_at': created.isoformat(), 'restore_verified': bool(record.get('restore_verified')), 'recent': created >= now() - timedelta(hours=36)}
    except (OSError, ValueError, KeyError, TypeError): pass
    recent = bool(heartbeat and heartbeat.last_seen_at >= now() - timedelta(seconds=90))
    return {'worker': {'online': recent, 'error': bool(heartbeat and heartbeat.error), 'dispatch_enabled': bool(heartbeat and heartbeat.dispatch_enabled),
        'last_seen_at': heartbeat.last_seen_at.isoformat() if heartbeat else None,
        'last_success_at': heartbeat.last_success_at.isoformat() if heartbeat and heartbeat.last_success_at else None},
        'backup': backup, 'jobs': counts(AutomationJob, AutomationJob.status), 'outbox': counts(InboxMessage, InboxMessage.status), 'channels': channels,
        'alerts': (['O processamento contínuo está sem sinal recente.'] if not recent else []) +
                  (['O worker registrou uma falha no último ciclo.'] if heartbeat and heartbeat.error else []) +
                  (['Não há backup recente com restauração validada.'] if not backup or not backup['recent'] or not backup['restore_verified'] else [])}


@bp.get('/communication-suppressions')
@require('owner', 'admin')
def suppressions(): return page(query(CommunicationSuppression).order_by(CommunicationSuppression.created_at.desc()))


@bp.post('/communication-suppressions')
@require('owner', 'admin')
def suppress():
    data = payload(SuppressionSchema); contact = get(Contact, data['contact_id'])
    from ..services.booking import lock
    lock('suppression:' + g.workspace_id + ':' + contact.id + ':' + data['channel'])
    row = query(CommunicationSuppression).filter_by(contact_id=contact.id, channel=data['channel']).first()
    if not row: row = add(CommunicationSuppression, data)
    # Pending outbound messages are checked again at dispatch as well.
    threads = query(InboxThread).filter_by(contact_id=contact.id, channel=data['channel']).with_entities(InboxThread.id)
    query(InboxMessage).filter(InboxMessage.thread_id.in_(threads), InboxMessage.direction == 'out', InboxMessage.status.in_(['queued', 'blocked'])).update(
        {'status': 'cancelled', 'error': 'Contato não autoriza mensagens neste canal.'}, synchronize_session=False)
    return commit(row, 201)


@bp.delete('/communication-suppressions/<uuid:identifier>')
@require('owner', 'admin')
def unsuppress(identifier):
    row = get(CommunicationSuppression, identifier)
    audit('remove_suppression', row)
    db.session.delete(row); db.session.commit()
    return '', 204
