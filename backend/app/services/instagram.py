"""Instagram Login API. Credentials never leave the server; no automatic DM sends."""

import hashlib
import json
from datetime import datetime, timedelta, timezone

import requests
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app
from sqlalchemy.orm.attributes import flag_modified

from ..common import APIError
from ..extensions import db
from ..models import (
    CommunicationSuppression,
    Contact,
    InboxMessage,
    InboxThread,
    InstagramComment,
    InstagramConnection,
    InstagramEvent,
    Workspace,
    now,
)


def configured():
    return all(
        current_app.config.get(k) for k in ('INSTAGRAM_APP_ID', 'INSTAGRAM_APP_SECRET', 'INSTAGRAM_ENCRYPTION_KEY')
    )


def cipher():
    return Fernet(current_app.config['INSTAGRAM_ENCRYPTION_KEY'].encode())


def graph(path, token, method='GET', **kwargs):
    url = 'https://graph.instagram.com/' + current_app.config['INSTAGRAM_API_VERSION'] + '/' + path
    try:
        response = requests.request(
            method, url, headers={'Authorization': 'Bearer ' + token}, timeout=(5, 20), **kwargs
        )
        data = response.json()
        if not response.ok or 'error' in data:
            raise APIError('O Instagram recusou a solicitação. Confira a autorização e as permissões da conta.', 502)
        return data
    except (requests.RequestException, ValueError):
        raise APIError('Não foi possível confirmar a solicitação no Instagram.', 502) from None


def profile(token):
    data = graph('me', token, params={'fields': 'id,user_id,username,name,profile_picture_url'})
    if not str(data.get('user_id', '')).isdigit() or not data.get('username'):
        raise APIError('O token não identificou uma conta profissional do Instagram.', 422)
    return data


def apply_account(row, data):
    row.name = (data.get('name') or '').strip()[:150] or row.name
    row.profile_picture_url = data.get('profile_picture_url') or row.profile_picture_url
    row.profile_synced_at = now()
    if data.get('username'):
        row.username = data['username']


def fetch_account(token):
    """Name, @username and picture of the connected account. Best effort with short timeouts."""
    try:
        response = requests.get(
            f'https://graph.instagram.com/{current_app.config["INSTAGRAM_API_VERSION"]}/me',
            params={'fields': 'user_id,username,name,profile_picture_url'},
            headers={'Authorization': 'Bearer ' + token},
            timeout=(2, 5),
        )
        data = response.json()
        return None if not response.ok or 'error' in data else data
    except (requests.RequestException, ValueError):
        return None


def refresh_account(row, max_age_hours=6):
    """Keeps the connection card current; picture links from Instagram expire, so they are renewed periodically."""
    if not row or not row.active or not row.encrypted_token:
        return
    if (
        row.profile_synced_at
        and row.name
        and row.profile_picture_url
        and row.profile_synced_at > now() - timedelta(hours=max_age_hours)
    ):
        return
    data = fetch_account(cipher().decrypt(row.encrypted_token.encode()).decode())
    if data:
        apply_account(row, data)
        db.session.commit()


def connect(workspace_id, token, expires_in=None):
    data = profile(token)
    identifier = str(data['user_id'])
    other = InstagramConnection.query.filter_by(instagram_id=identifier).first()
    if other and other.workspace_id != workspace_id:
        raise APIError('Este Instagram já está vinculado a outra conta de cliente.', 409)
    row = InstagramConnection.query.filter_by(workspace_id=workspace_id).first()
    if row and row.instagram_id != identifier and row.active:
        raise APIError('Desvincule o perfil atual antes de conectar outro Instagram.', 409)
    if not row:
        row = InstagramConnection(workspace_id=workspace_id, instagram_id=identifier)
        db.session.add(row)
    row.instagram_id = identifier
    row.username, row.encrypted_token, row.active = data['username'], cipher().encrypt(token.encode()).decode(), True
    row.expires_at = now() + timedelta(seconds=int(expires_in)) if expires_in else None
    apply_account(row, data)
    db.session.flush()
    return row


SUBSCRIBED_FIELDS = 'messages'


def subscription(connection):
    """Fields this app receives for the professional account, as reported by Instagram."""
    token = cipher().decrypt(connection.encrypted_token.encode()).decode()
    data = graph(connection.instagram_id + '/subscribed_apps', token)
    apps = data.get('data') or []
    mine = next(
        (item for item in apps if str(item.get('id')) == str(current_app.config.get('INSTAGRAM_APP_ID'))),
        apps[0] if apps else {},
    )
    return list(mine.get('subscribed_fields') or [])


def subscribe(connection):
    """Subscribes the account to message webhooks. Idempotent; required for Instagram Login deliveries."""
    token = cipher().decrypt(connection.encrypted_token.encode()).decode()
    graph(
        connection.instagram_id + '/subscribed_apps',
        token,
        method='POST',
        params={'subscribed_fields': SUBSCRIBED_FIELDS},
    )


def verify_delivery(connection):
    """Checks (and repairs) the message subscription, then reports what has actually arrived."""
    from sqlalchemy import func

    fields = subscription(connection)
    activated = False
    if 'messages' not in fields:
        subscribe(connection)
        fields, activated = subscription(connection), True
    count, last = (
        db.session.query(func.count(InstagramEvent.id), func.max(InstagramEvent.created_at))
        .filter_by(connection_id=connection.id)
        .one()
    )
    return {
        'subscribed': 'messages' in fields,
        'fields': fields,
        'activated': activated,
        'events': count,
        'last_event_at': last.isoformat() if last else None,
    }


def oauth_tokens(code):
    try:
        response = requests.post(
            'https://api.instagram.com/oauth/access_token',
            data={
                'client_id': current_app.config['INSTAGRAM_APP_ID'],
                'client_secret': current_app.config['INSTAGRAM_APP_SECRET'],
                'grant_type': 'authorization_code',
                'redirect_uri': current_app.config['INSTAGRAM_REDIRECT_URI'],
                'code': code,
            },
            timeout=(5, 20),
        )
        data = response.json()
        if not response.ok or not data.get('access_token'):
            raise APIError('Não foi possível concluir a autorização do Instagram. Conecte novamente.', 502)
        response = requests.get(
            'https://graph.instagram.com/access_token',
            params={
                'grant_type': 'ig_exchange_token',
                'client_secret': current_app.config['INSTAGRAM_APP_SECRET'],
                'access_token': data['access_token'],
            },
            timeout=(5, 20),
        )
        result = response.json()
        if not response.ok or not result.get('access_token') or not result.get('expires_in'):
            raise APIError('Não foi possível obter a autorização de longa duração. Conecte novamente.', 502)
        return result
    except (requests.RequestException, ValueError):
        raise APIError('O Instagram não confirmou a autorização. Tente conectar novamente.', 502) from None


def active_connection(workspace_id):
    row = InstagramConnection.query.filter_by(workspace_id=workspace_id, active=True).first()
    if not row or (row.expires_at and row.expires_at <= now()):
        raise APIError('Reconecte o Instagram desta conta.', 409)
    return row


def fetch_profile(connection, scoped_id):
    """Name and @username of a person who messaged the account (User Profile API). Best effort, short timeouts."""
    try:
        token = cipher().decrypt(connection.encrypted_token.encode()).decode()
        response = requests.get(
            f'https://graph.instagram.com/{current_app.config["INSTAGRAM_API_VERSION"]}/{scoped_id}',
            params={'fields': 'name,username'},
            headers={'Authorization': 'Bearer ' + token},
            timeout=(2, 4),
        )
        data = response.json()
        if not response.ok or 'error' in data:
            return None
        name, username = (data.get('name') or '').strip(), (data.get('username') or '').strip()
        return {'name': name, 'username': username} if name or username else None
    except (requests.RequestException, ValueError, InvalidToken):
        return None


def apply_profile(contact, scoped_id, profile):
    """Replaces the placeholder name; never overwrites a name someone typed."""
    if not profile:
        return
    fields = dict(contact.custom_fields or {})
    if profile['username']:
        fields['instagram_username'] = profile['username']
    if profile['name']:
        fields['instagram_name'] = profile['name']
    contact.custom_fields = fields
    if contact.name == 'Instagram ' + scoped_id:
        contact.name = (profile['name'] or '@' + profile['username'])[:180]


def process_event(connection, item, kind):
    # For messages, mid is stable across webhook retries even if envelope timestamps change.
    mid = item.get('message', {}).get('mid') if kind == 'messaging' else None
    key = hashlib.sha256(
        (connection.id + ':' + (str(mid) if mid else json.dumps(item, sort_keys=True))).encode()
    ).hexdigest()
    if InstagramEvent.query.filter_by(event_key=key).first():
        return
    db.session.add(
        InstagramEvent(
            workspace_id=connection.workspace_id, connection_id=connection.id, event_key=key, kind=kind, payload=item
        )
    )
    if kind in ('comments', 'live_comments'):
        process_comment(connection, item.get('value') or {})
        return
    if kind != 'messaging':
        return  # Other subscribed events retained, never silently discarded.
    ingest_message(connection, item, key)


def ingest_message(connection, item, key, historical=False):
    """Materialize inbound DMs and owner echoes; recording an echo never sends or starts an automation."""
    message = item.get('message') or {}
    mid = message.get('mid')
    if not mid or message.get('is_deleted'):
        return False
    sender = str((item.get('sender') or {}).get('id', ''))
    recipient = str((item.get('recipient') or {}).get('id', ''))
    outgoing = sender == connection.instagram_id
    if outgoing:
        peer = recipient
    else:
        if recipient != connection.instagram_id or message.get('is_echo'):
            return False
        peer = sender
    if not peer.isdigit() or peer == connection.instagram_id:
        return False
    content = message.get('text') or (
        ('[Anexo enviado no Instagram]' if outgoing else '[Anexo recebido no Instagram]')
        if message.get('attachments')
        else '[Mensagem do Instagram]'
    )
    try:
        occurred = datetime.fromtimestamp(float(item.get('timestamp')) / 1000, timezone.utc)
        if occurred > now() + timedelta(minutes=5):
            raise ValueError()
    except (ValueError, TypeError, OSError, OverflowError):
        raise APIError('Data de evento inválida.', 422) from None
    thread = (
        InboxThread.query.filter_by(
            workspace_id=connection.workspace_id, channel='instagram', address=connection.instagram_id + ':' + peer
        )
        .with_for_update()
        .first()
    )
    if not thread:
        thread = InboxThread(
            workspace_id=connection.workspace_id,
            channel='instagram',
            address=connection.instagram_id + ':' + peer,
            updated_at=occurred,
        )
        db.session.add(thread)
        db.session.flush()
    previous_updated = thread.updated_at
    # The provider MID, not the origin of the send, identifies the same message.
    existing = InboxMessage.query.filter_by(
        workspace_id=connection.workspace_id, thread_id=thread.id, provider_id=str(mid)[:180]
    ).first()
    if existing:
        if outgoing and existing.direction == 'out' and existing.status in ('sending', 'unknown'):
            existing.status, existing.error = 'sent', None
        return False
    if not outgoing:
        contact = db.session.get(Contact, thread.contact_id) if thread.contact_id else None
        if not contact:
            earlier = (
                InstagramComment.query.filter(
                    InstagramComment.connection_id == connection.id,
                    InstagramComment.from_id == peer,
                    InstagramComment.contact_id.isnot(None),
                )
                .order_by(InstagramComment.created_at)
                .first()
            )
            contact = db.session.get(Contact, earlier.contact_id) if earlier else None
            if contact and (contact.archived or contact.workspace_id != connection.workspace_id):
                contact = None
            if not contact:
                contact = Contact(
                    workspace_id=connection.workspace_id,
                    name='Instagram ' + peer,
                    source='Instagram',
                    custom_fields={'instagram_scoped_id': peer, 'instagram_account_id': connection.instagram_id},
                )
                db.session.add(contact)
                db.session.flush()
            thread.contact_id = contact.id
        if not historical and (contact.name.startswith('@') or contact.name == 'Instagram ' + peer):
            apply_profile(contact, peer, fetch_profile(connection, peer))
    row = InboxMessage(
        workspace_id=connection.workspace_id,
        thread_id=thread.id,
        direction='out' if outgoing else 'in',
        content=str(content)[:20000],
        status='sent' if outgoing else 'received',
        provider_id=str(mid)[:180],
        idempotency_key='instagram:' + key,
        created_at=occurred,
        scheduled_at=occurred,
    )
    db.session.add(row)
    db.session.flush()
    # Backfilled history must not move an old conversation ahead of newer messages.
    thread.updated_at = max(previous_updated, occurred)
    flag_modified(thread, 'updated_at')  # Override Base.onupdate, even when the date is unchanged.
    if not outgoing and not historical:
        thread.status = 'open'  # A new message reopens a closed conversation, as on WhatsApp.
        from .notifications import record

        record(thread, row, 'inbox')
        contact = db.session.get(Contact, thread.contact_id)
        if contact and not contact.archived:
            from .automations import received_reply

            received_reply(connection.workspace_id, contact, row.id)
    return True


def recover_outgoing_events(connection):
    """Replay preserved outbound events only; caller commits, no provider calls or automations."""
    workspace = db.session.get(Workspace, connection.workspace_id)
    if not connection.active or not workspace or not workspace.active:
        return 0
    restored = 0
    events = (
        InstagramEvent.query.filter_by(
            connection_id=connection.id, workspace_id=connection.workspace_id, kind='messaging'
        )
        .order_by(InstagramEvent.created_at)
        .all()
    )
    for event in events:
        item = event.payload or {}
        if str((item.get('sender') or {}).get('id', '')) == connection.instagram_id:
            restored += int(ingest_message(connection, item, event.event_key))
    return restored


def confirm_reply(row, provider_id):
    """An echo can arrive while the send HTTP call is still running. Keep the original platform claim."""
    InboxThread.query.filter_by(id=row.thread_id, workspace_id=row.workspace_id).with_for_update().one()
    echoes = (
        InboxMessage.query.filter_by(
            workspace_id=row.workspace_id, thread_id=row.thread_id, direction='out', provider_id=str(provider_id)[:180]
        )
        .filter(InboxMessage.id != row.id)
        .all()
    )
    for echo in echoes:
        if echo.idempotency_key.startswith('instagram:') and echo.sent_by_id is None:
            db.session.delete(echo)
    row.provider_id, row.status, row.error = str(provider_id)[:180], 'sent', None


COMMENT_REPLIES_PER_HOUR = 60


def process_comment(connection, value):
    """Stores a top-level comment from someone else, links a contact, and fires `instagram.comment` automations."""
    comment_id, author = str(value.get('id') or ''), value.get('from') or {}
    sender, username = str(author.get('id') or ''), str(author.get('username') or '')[:150]
    if not comment_id or not sender.isdigit() or sender == connection.instagram_id or value.get('parent_id'):
        return  # Own comments and replies never trigger anything: no loops.
    if InstagramComment.query.filter_by(comment_id=comment_id).first():
        return
    contact = None
    thread = InboxThread.query.filter_by(
        workspace_id=connection.workspace_id, channel='instagram', address=connection.instagram_id + ':' + sender
    ).first()
    if thread and thread.contact_id:
        contact = db.session.get(Contact, thread.contact_id)
    if not contact:
        earlier = (
            InstagramComment.query.filter_by(connection_id=connection.id, from_id=sender)
            .filter(InstagramComment.contact_id.isnot(None))
            .first()
        )
        contact = db.session.get(Contact, earlier.contact_id) if earlier else None
    if contact and contact.archived:
        return
    if not contact:
        contact = Contact(
            workspace_id=connection.workspace_id,
            name=('@' + username) if username else 'Instagram ' + sender,
            source='Instagram',
            custom_fields={
                'instagram_scoped_id': sender,
                'instagram_account_id': connection.instagram_id,
                **({'instagram_username': username} if username else {}),
            },
        )
        db.session.add(contact)
        db.session.flush()
    row = InstagramComment(
        workspace_id=connection.workspace_id,
        connection_id=connection.id,
        comment_id=comment_id[:80],
        media_id=str((value.get('media') or {}).get('id') or '')[:80] or None,
        from_id=sender,
        username=username or None,
        text=str(value.get('text') or '')[:2200],
        contact_id=contact.id,
    )
    db.session.add(row)
    db.session.flush()
    from .automations import emit

    emit(
        connection.workspace_id,
        'instagram.comment',
        comment_id,
        contact,
        source='Instagram',
        context={'text': row.text, 'media_id': row.media_id, 'comment_id': comment_id},
    )


def dm_message(text, buttons=None, quick_replies=None):
    """The Send API `message`: plain text, or a button template when there are link buttons; quick replies ride along."""
    if buttons:
        message = {
            'attachment': {
                'type': 'template',
                'payload': {
                    'template_type': 'button',
                    'text': text,
                    'buttons': [{'type': 'web_url', 'url': b['url'], 'title': b['title']} for b in buttons],
                },
            }
        }
    else:
        message = {'text': text}
    if quick_replies:
        message['quick_replies'] = [{'content_type': 'text', 'title': q, 'payload': q} for q in quick_replies]
    return message


def dm_record(text, buttons=None, quick_replies=None):
    """How a sent message with buttons reads in the inbox, which stores plain text."""
    lines = [text]
    if buttons:
        lines.append('Botões: ' + ' · '.join(f'{b["title"]} ({b["url"]})' for b in buttons))
    if quick_replies:
        lines.append('Respostas rápidas: ' + ' · '.join(quick_replies))
    return '\n\n'.join(lines)


def comment_action(kind, comment, contact, content, workspace, buttons=None, quick_replies=None):
    """Runs one automated comment action. Returns the comment id on success, or None when it no longer applies."""
    if not comment:
        raise APIError('Comentário indisponível.', 422)
    connection = InstagramConnection.query.filter_by(id=comment.connection_id, workspace_id=workspace.id).first()
    if not connection or not connection.active or (connection.expires_at and connection.expires_at <= now()):
        raise APIError('Reconecte o Instagram desta conta.', 409)
    sent_field = 'replied_at' if kind == 'reply_comment' else 'private_replied_at'
    if getattr(comment, sent_field):
        return None  # Already answered once; never answer the same comment twice.
    from sqlalchemy import func

    recent = (
        db.session.query(func.count(InstagramComment.id))
        .filter(
            InstagramComment.connection_id == connection.id,
            db.or_(
                InstagramComment.replied_at > now() - timedelta(hours=1),
                InstagramComment.private_replied_at > now() - timedelta(hours=1),
            ),
        )
        .scalar()
    )
    if recent >= COMMENT_REPLIES_PER_HOUR:
        raise APIError('Limite de respostas automáticas por hora atingido.', 429)
    from .communications import render

    text = render(content, contact).replace('{{username}}', comment.username or '').strip()
    if not text or len(text.encode()) > 1000:
        raise APIError('Texto da resposta inválido.', 422)
    token = cipher().decrypt(connection.encrypted_token.encode()).decode()
    if kind == 'reply_comment':
        result = graph(comment.comment_id + '/replies', token, method='POST', params={'message': text})
        setattr(comment, sent_field, now())
        return comment.id
    result = graph(
        connection.instagram_id + '/messages',
        token,
        method='POST',
        json={'recipient': {'comment_id': comment.comment_id}, 'message': dm_message(text, buttons, quick_replies)},
    )
    setattr(comment, sent_field, now())
    thread = InboxThread.query.filter_by(
        workspace_id=workspace.id, channel='instagram', address=connection.instagram_id + ':' + comment.from_id
    ).first()
    if not thread:
        thread = InboxThread(
            workspace_id=workspace.id,
            channel='instagram',
            address=connection.instagram_id + ':' + comment.from_id,
            contact_id=contact.id,
        )
        db.session.add(thread)
        db.session.flush()
    elif not thread.contact_id:
        thread.contact_id = contact.id
    message_id = str(result.get('message_id') or 'private-' + comment.comment_id)[:180]
    message = InboxMessage(
        workspace_id=workspace.id,
        thread_id=thread.id,
        direction='out',
        content=dm_record(text, buttons, quick_replies),
        status='sent',
        provider_id=message_id,
        idempotency_key='instagram-private:' + comment.comment_id,
    )
    db.session.add(message)
    db.session.flush()
    confirm_reply(message, message_id)
    thread.updated_at = now()
    return comment.id


def automation_message(contact, content, workspace, key, buttons=None, quick_replies=None):
    """An automated direct message in the contact's Instagram conversation. Returns None when there is no
    conversation or Instagram's 24-hour window has closed: those steps are dismissed, not failed."""
    connection = active_connection(workspace.id)
    thread = (
        InboxThread.query.filter_by(workspace_id=workspace.id, channel='instagram', contact_id=contact.id)
        .filter(InboxThread.address.startswith(connection.instagram_id + ':'))
        .order_by(InboxThread.updated_at.desc())
        .first()
    )
    if not thread:
        return None
    last = (
        InboxMessage.query.filter_by(workspace_id=workspace.id, thread_id=thread.id, direction='in')
        .order_by(InboxMessage.created_at.desc())
        .first()
    )
    if not last or last.created_at < now() - timedelta(hours=24):
        return None
    if CommunicationSuppression.query.filter_by(
        workspace_id=workspace.id, contact_id=contact.id, channel='instagram'
    ).first():
        return None
    existing = InboxMessage.query.filter_by(workspace_id=workspace.id, idempotency_key=key).first()
    if existing:
        return existing.id
    from .communications import render

    text = render(content, contact).strip()
    if not text or len(text.encode()) > 1000:
        raise APIError('Texto da mensagem inválido.', 422)
    result = graph(
        connection.instagram_id + '/messages',
        cipher().decrypt(connection.encrypted_token.encode()).decode(),
        method='POST',
        json={'recipient': {'id': thread.address.split(':')[1]}, 'message': dm_message(text, buttons, quick_replies)},
    )
    if not result.get('message_id'):
        raise APIError('Sem confirmação do Instagram.', 502)
    row = InboxMessage(
        workspace_id=workspace.id,
        thread_id=thread.id,
        direction='out',
        content=dm_record(text, buttons, quick_replies),
        status='sent',
        idempotency_key=key,
    )
    db.session.add(row)
    db.session.flush()
    confirm_reply(row, result['message_id'])
    thread.updated_at = now()
    return row.id


def receive(body):
    if not isinstance(body, dict) or body.get('object') != 'instagram' or not isinstance(body.get('entry'), list):
        raise APIError('Evento do Instagram inválido.', 422)
    for entry in body['entry']:
        connection = (
            InstagramConnection.query.filter_by(instagram_id=str(entry.get('id')), active=True)
            .with_for_update()
            .first()
        )
        if not connection:
            continue
        workspace = db.session.get(Workspace, connection.workspace_id)
        if not workspace or not workspace.active:
            continue
        for item in entry.get('messaging', []):
            process_event(connection, item, 'messaging')
        for item in entry.get('changes', []):
            process_event(connection, item, str(item.get('field', 'change'))[:40])


def send_reply(thread, content, key, user_id):
    if len(content) > 1000:
        raise APIError('A resposta do Instagram aceita até 1.000 caracteres.', 422)
    connection = active_connection(thread.workspace_id)
    if thread.address.split(':')[0] != connection.instagram_id:
        raise APIError('Perfil da conversa não corresponde à conexão.', 409)
    existing = InboxMessage.query.filter_by(workspace_id=thread.workspace_id, idempotency_key=key).first()
    if existing:
        if existing.thread_id != thread.id or existing.direction != 'out' or existing.content != content:
            raise APIError('Chave utilizada por outra mensagem.', 409)
        return existing
    last = (
        InboxMessage.query.filter_by(workspace_id=thread.workspace_id, thread_id=thread.id, direction='in')
        .order_by(InboxMessage.created_at.desc())
        .first()
    )
    if not last or last.created_at < now() - timedelta(hours=24):
        raise APIError('A janela de resposta de 24 horas do Instagram encerrou. Aguarde uma nova mensagem.', 409)
    contact = db.session.get(Contact, thread.contact_id)

    if (
        not contact
        or contact.archived
        or CommunicationSuppression.query.filter_by(
            workspace_id=thread.workspace_id, contact_id=contact.id, channel='instagram'
        ).first()
    ):
        raise APIError('Este contato está indisponível para respostas.', 409)
    row = InboxMessage(
        workspace_id=thread.workspace_id,
        thread_id=thread.id,
        direction='out',
        content=content,
        status='sending',
        idempotency_key=key,
        sent_by_id=user_id,
    )
    db.session.add(row)
    db.session.commit()  # Persist claim before external I/O; never retry an ambiguous outcome.
    try:
        result = graph(
            connection.instagram_id + '/messages',
            cipher().decrypt(connection.encrypted_token.encode()).decode(),
            method='POST',
            json={'recipient': {'id': thread.address.split(':')[1]}, 'message': {'text': content}},
        )
        if not result.get('message_id'):
            raise APIError('Sem confirmação.', 502)
        confirm_reply(row, result['message_id'])
    except Exception as error:  # delivery boundary: any failure after the call leaves the message 'unknown'
        current_app.logger.warning('Falha ao enviar resposta no Instagram: %s', type(error).__name__)
        row.status, row.error = 'unknown', 'Envio sem confirmação. Confira no Instagram antes de reenviar.'
    thread.updated_at = now()
    db.session.commit()
    return row
