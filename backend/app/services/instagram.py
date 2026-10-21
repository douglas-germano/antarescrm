"""Instagram Login API. Credentials never leave the server; no automatic DM sends."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
import requests
from cryptography.fernet import Fernet
from flask import current_app
from ..common import APIError
from ..extensions import db
from ..models import InstagramComment, InstagramConnection, InstagramEvent, InboxMessage, InboxThread, Contact, Workspace, now


def configured():
    return all(current_app.config.get(k) for k in ('INSTAGRAM_APP_ID', 'INSTAGRAM_APP_SECRET', 'INSTAGRAM_ENCRYPTION_KEY'))


def cipher():
    return Fernet(current_app.config['INSTAGRAM_ENCRYPTION_KEY'].encode())


def graph(path, token, method='GET', **kwargs):
    url = 'https://graph.instagram.com/' + current_app.config['INSTAGRAM_API_VERSION'] + '/' + path
    try:
        response = requests.request(method, url, headers={'Authorization': 'Bearer ' + token}, timeout=(5, 20), **kwargs)
        data = response.json()
        if not response.ok or 'error' in data:
            raise APIError('O Instagram recusou a solicitação. Confira a autorização e as permissões da conta.', 502)
        return data
    except (requests.RequestException, ValueError):
        raise APIError('Não foi possível confirmar a solicitação no Instagram.', 502)


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
        response = requests.get(f"https://graph.instagram.com/{current_app.config['INSTAGRAM_API_VERSION']}/me",
            params={'fields': 'user_id,username,name,profile_picture_url'}, headers={'Authorization': 'Bearer ' + token}, timeout=(2, 5))
        data = response.json()
        return None if not response.ok or 'error' in data else data
    except Exception:
        return None


def refresh_account(row, max_age_hours=6):
    """Keeps the connection card current; picture links from Instagram expire, so they are renewed periodically."""
    if not row or not row.active or not row.encrypted_token:
        return
    if row.profile_synced_at and row.name and row.profile_picture_url and row.profile_synced_at > now() - timedelta(hours=max_age_hours):
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
    mine = next((item for item in apps if str(item.get('id')) == str(current_app.config.get('INSTAGRAM_APP_ID'))), apps[0] if apps else {})
    return list(mine.get('subscribed_fields') or [])


def subscribe(connection):
    """Subscribes the account to message webhooks. Idempotent; required for Instagram Login deliveries."""
    token = cipher().decrypt(connection.encrypted_token.encode()).decode()
    graph(connection.instagram_id + '/subscribed_apps', token, method='POST', params={'subscribed_fields': SUBSCRIBED_FIELDS})


def verify_delivery(connection):
    """Checks (and repairs) the message subscription, then reports what has actually arrived."""
    from sqlalchemy import func
    fields = subscription(connection)
    activated = False
    if 'messages' not in fields:
        subscribe(connection)
        fields, activated = subscription(connection), True
    count, last = db.session.query(func.count(InstagramEvent.id), func.max(InstagramEvent.created_at)).filter_by(connection_id=connection.id).one()
    return {'subscribed': 'messages' in fields, 'fields': fields, 'activated': activated, 'events': count,
            'last_event_at': last.isoformat() if last else None}


def oauth_tokens(code):
    try:
        response = requests.post('https://api.instagram.com/oauth/access_token', data={
            'client_id': current_app.config['INSTAGRAM_APP_ID'], 'client_secret': current_app.config['INSTAGRAM_APP_SECRET'],
            'grant_type': 'authorization_code', 'redirect_uri': current_app.config['INSTAGRAM_REDIRECT_URI'], 'code': code,
        }, timeout=(5, 20))
        data = response.json()
        if not response.ok or not data.get('access_token'):
            raise APIError('Não foi possível concluir a autorização do Instagram. Conecte novamente.', 502)
        response = requests.get('https://graph.instagram.com/access_token', params={
            'grant_type': 'ig_exchange_token', 'client_secret': current_app.config['INSTAGRAM_APP_SECRET'], 'access_token': data['access_token'],
        }, timeout=(5, 20))
        result = response.json()
        if not response.ok or not result.get('access_token') or not result.get('expires_in'):
            raise APIError('Não foi possível obter a autorização de longa duração. Conecte novamente.', 502)
        return result
    except (requests.RequestException, ValueError):
        raise APIError('O Instagram não confirmou a autorização. Tente conectar novamente.', 502)


def active_connection(workspace_id):
    row = InstagramConnection.query.filter_by(workspace_id=workspace_id, active=True).first()
    if not row or (row.expires_at and row.expires_at <= now()):
        raise APIError('Reconecte o Instagram desta conta.', 409)
    return row


def fetch_profile(connection, scoped_id):
    """Name and @username of a person who messaged the account (User Profile API). Best effort, short timeouts."""
    try:
        token = cipher().decrypt(connection.encrypted_token.encode()).decode()
        response = requests.get(f"https://graph.instagram.com/{current_app.config['INSTAGRAM_API_VERSION']}/{scoped_id}",
            params={'fields': 'name,username'}, headers={'Authorization': 'Bearer ' + token}, timeout=(2, 4))
        data = response.json()
        if not response.ok or 'error' in data:
            return None
        name, username = (data.get('name') or '').strip(), (data.get('username') or '').strip()
        return {'name': name, 'username': username} if name or username else None
    except Exception:
        return None


def apply_profile(contact, scoped_id, profile):
    """Replaces the placeholder name; never overwrites a name someone typed."""
    if not profile:
        return
    fields = dict(contact.custom_fields or {})
    if profile['username']: fields['instagram_username'] = profile['username']
    if profile['name']: fields['instagram_name'] = profile['name']
    contact.custom_fields = fields
    if contact.name == 'Instagram ' + scoped_id:
        contact.name = (profile['name'] or '@' + profile['username'])[:180]


def process_event(connection, item, kind):
    # For messages, mid is stable across webhook retries even if envelope timestamps change.
    mid = item.get('message', {}).get('mid') if kind == 'messaging' else None
    key = hashlib.sha256((connection.id + ':' + (str(mid) if mid else json.dumps(item, sort_keys=True))).encode()).hexdigest()
    if InstagramEvent.query.filter_by(event_key=key).first(): return
    db.session.add(InstagramEvent(workspace_id=connection.workspace_id, connection_id=connection.id,
        event_key=key, kind=kind, payload=item))
    if kind in ('comments', 'live_comments'):
        process_comment(connection, item.get('value') or {})
        return
    if kind != 'messaging': return  # Other subscribed events retained, never silently discarded.
    message = item.get('message') or {}
    if not mid or message.get('is_echo') or message.get('is_deleted'): return
    sender = str((item.get('sender') or {}).get('id', ''))
    recipient = str((item.get('recipient') or {}).get('id', ''))
    if recipient != connection.instagram_id or not sender.isdigit() or sender == recipient: return
    content = message.get('text') or ('[Anexo recebido no Instagram]' if message.get('attachments') else '[Mensagem do Instagram]')
    timestamp = item.get('timestamp')
    try:
        occurred = datetime.fromtimestamp(float(timestamp) / 1000, timezone.utc)
        if occurred > now() + timedelta(minutes=5): raise ValueError()
    except (ValueError, TypeError, OSError, OverflowError):
        raise APIError('Data de evento inválida.', 422)
    address = connection.instagram_id + ':' + sender
    thread = InboxThread.query.filter_by(workspace_id=connection.workspace_id, channel='instagram', address=address).first()
    if not thread:
        # Someone who commented first already has a contact: keep one person, one contact.
        earlier = InstagramComment.query.filter(InstagramComment.connection_id == connection.id, InstagramComment.from_id == sender,
                                                InstagramComment.contact_id.isnot(None)).order_by(InstagramComment.created_at).first()
        contact = db.session.get(Contact, earlier.contact_id) if earlier else None
        if contact and contact.archived: contact = None
        if not contact:
            contact = Contact(workspace_id=connection.workspace_id, name='Instagram ' + sender, source='Instagram',
                custom_fields={'instagram_scoped_id': sender, 'instagram_account_id': connection.instagram_id})
            apply_profile(contact, sender, fetch_profile(connection, sender))
            db.session.add(contact); db.session.flush()
        elif contact.name.startswith('@') or contact.name == 'Instagram ' + sender:
            apply_profile(contact, sender, fetch_profile(connection, sender))
        thread = InboxThread(workspace_id=connection.workspace_id, channel='instagram', address=address, contact_id=contact.id)
        db.session.add(thread); db.session.flush()
    thread.updated_at = now()
    existing = db.session.get(Contact, thread.contact_id) if thread.contact_id else None
    if existing and existing.name == 'Instagram ' + sender:  # Placeholder from before names were fetched.
        apply_profile(existing, sender, fetch_profile(connection, sender))
    row = InboxMessage(workspace_id=connection.workspace_id, thread_id=thread.id, direction='in',
        content=str(content)[:20000], status='received', provider_id=str(mid)[:180], idempotency_key='instagram:' + key,
        created_at=occurred, scheduled_at=occurred)
    db.session.add(row); db.session.flush()
    contact = db.session.get(Contact, thread.contact_id)
    if contact and not contact.archived:
        from .automations import received_reply
        received_reply(connection.workspace_id, contact, row.id)


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
    thread = InboxThread.query.filter_by(workspace_id=connection.workspace_id, channel='instagram', address=connection.instagram_id + ':' + sender).first()
    if thread and thread.contact_id:
        contact = db.session.get(Contact, thread.contact_id)
    if not contact:
        earlier = InstagramComment.query.filter_by(connection_id=connection.id, from_id=sender).filter(InstagramComment.contact_id.isnot(None)).first()
        contact = db.session.get(Contact, earlier.contact_id) if earlier else None
    if contact and contact.archived: return
    if not contact:
        contact = Contact(workspace_id=connection.workspace_id, name=('@' + username) if username else 'Instagram ' + sender, source='Instagram',
            custom_fields={'instagram_scoped_id': sender, 'instagram_account_id': connection.instagram_id, **({'instagram_username': username} if username else {})})
        db.session.add(contact); db.session.flush()
    row = InstagramComment(workspace_id=connection.workspace_id, connection_id=connection.id, comment_id=comment_id[:80],
        media_id=str((value.get('media') or {}).get('id') or '')[:80] or None, from_id=sender, username=username or None,
        text=str(value.get('text') or '')[:2200], contact_id=contact.id)
    db.session.add(row); db.session.flush()
    from .automations import emit
    emit(connection.workspace_id, 'instagram.comment', comment_id, contact, source='Instagram',
         context={'text': row.text, 'media_id': row.media_id, 'comment_id': comment_id})


def comment_action(kind, comment, contact, content, workspace):
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
    recent = db.session.query(func.count(InstagramComment.id)).filter(InstagramComment.connection_id == connection.id,
        db.or_(InstagramComment.replied_at > now() - timedelta(hours=1), InstagramComment.private_replied_at > now() - timedelta(hours=1))).scalar()
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
    result = graph(connection.instagram_id + '/messages', token, method='POST',
        json={'recipient': {'comment_id': comment.comment_id}, 'message': {'text': text}})
    setattr(comment, sent_field, now())
    thread = InboxThread.query.filter_by(workspace_id=workspace.id, channel='instagram', address=connection.instagram_id + ':' + comment.from_id).first()
    if not thread:
        thread = InboxThread(workspace_id=workspace.id, channel='instagram', address=connection.instagram_id + ':' + comment.from_id, contact_id=contact.id)
        db.session.add(thread); db.session.flush()
    message_id = str(result.get('message_id') or 'private-' + comment.comment_id)[:180]
    db.session.add(InboxMessage(workspace_id=workspace.id, thread_id=thread.id, direction='out', content=text, status='sent',
        provider_id=message_id, idempotency_key='instagram-private:' + comment.comment_id))
    thread.updated_at = now()
    return comment.id


def receive(body):
    if not isinstance(body, dict) or body.get('object') != 'instagram' or not isinstance(body.get('entry'), list):
        raise APIError('Evento do Instagram inválido.', 422)
    for entry in body['entry']:
        connection = InstagramConnection.query.filter_by(instagram_id=str(entry.get('id')), active=True).with_for_update().first()
        if not connection: continue
        workspace = db.session.get(Workspace, connection.workspace_id)
        if not workspace or not workspace.active: continue
        for item in entry.get('messaging', []): process_event(connection, item, 'messaging')
        for item in entry.get('changes', []): process_event(connection, item, str(item.get('field', 'change'))[:40])


def send_reply(thread, content, key, user_id):
    if len(content) > 1000: raise APIError('A resposta do Instagram aceita até 1.000 caracteres.', 422)
    connection = active_connection(thread.workspace_id)
    if thread.address.split(':')[0] != connection.instagram_id: raise APIError('Perfil da conversa não corresponde à conexão.', 409)
    existing = InboxMessage.query.filter_by(workspace_id=thread.workspace_id, idempotency_key=key).first()
    if existing:
        if existing.thread_id != thread.id or existing.direction != 'out' or existing.content != content:
            raise APIError('Chave utilizada por outra mensagem.', 409)
        return existing
    last = InboxMessage.query.filter_by(workspace_id=thread.workspace_id, thread_id=thread.id, direction='in').order_by(InboxMessage.created_at.desc()).first()
    if not last or last.created_at < now() - timedelta(hours=24):
        raise APIError('A janela de resposta de 24 horas do Instagram encerrou. Aguarde uma nova mensagem.', 409)
    contact = db.session.get(Contact, thread.contact_id)
    from ..models import CommunicationSuppression
    if not contact or contact.archived or CommunicationSuppression.query.filter_by(workspace_id=thread.workspace_id, contact_id=contact.id, channel='instagram').first():
        raise APIError('Este contato está indisponível para respostas.', 409)
    row = InboxMessage(workspace_id=thread.workspace_id, thread_id=thread.id, direction='out', content=content,
        status='sending', idempotency_key=key, sent_by_id=user_id)
    db.session.add(row); db.session.commit()  # Persist claim before external I/O; never retry an ambiguous outcome.
    try:
        result = graph(connection.instagram_id + '/messages', cipher().decrypt(connection.encrypted_token.encode()).decode(),
            method='POST', json={'recipient': {'id': thread.address.split(':')[1]}, 'message': {'text': content}})
        if not result.get('message_id'): raise APIError('Sem confirmação.', 502)
        row.provider_id, row.status = result['message_id'], 'sent'
    except Exception:
        row.status, row.error = 'unknown', 'Envio sem confirmação. Confira no Instagram antes de reenviar.'
    thread.updated_at = now()
    db.session.commit()
    return row
