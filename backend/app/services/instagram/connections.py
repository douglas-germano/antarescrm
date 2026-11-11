"""Instagram connections: account connection and webhook subscription."""

from datetime import timedelta

from flask import current_app

from ...common import APIError
from ...extensions import db
from ...models import InstagramConnection, InstagramEvent, now
from . import client, profiles

SUBSCRIBED_FIELDS = 'messages'


def connect(workspace_id, token, expires_in=None, scopes=None):
    """Links (or re-authorizes) a professional account. A workspace may hold several accounts; one account
    belongs to a single workspace, so client data never mixes."""
    data = client.profile(token)
    identifier = str(data['user_id'])
    row = InstagramConnection.query.filter_by(instagram_id=identifier).first()
    if row and row.workspace_id != workspace_id:
        raise APIError('Este Instagram já está vinculado a outra conta de cliente.', 409)
    if not row:
        row = InstagramConnection(workspace_id=workspace_id, instagram_id=identifier)
        db.session.add(row)
    row.username, row.encrypted_token, row.active = (
        data['username'],
        client.cipher().encrypt(token.encode()).decode(),
        True,
    )
    row.expires_at = now() + timedelta(seconds=int(expires_in)) if expires_in else None
    if scopes:
        row.scopes = ','.join(sorted({s.strip() for s in str(scopes).split(',') if s.strip()}))[:2000]
    profiles.apply_account(row, data)
    db.session.flush()
    return row


def subscription(connection):
    """Fields this app receives for the professional account, as reported by Instagram."""
    token = client.cipher().decrypt(connection.encrypted_token.encode()).decode()
    data = client.graph(connection.instagram_id + '/subscribed_apps', token)
    apps = data.get('data') or []
    mine = next(
        (item for item in apps if str(item.get('id')) == str(current_app.config.get('INSTAGRAM_APP_ID'))),
        apps[0] if apps else {},
    )
    return list(mine.get('subscribed_fields') or [])


def subscribe(connection):
    """Subscribes the account to message webhooks. Idempotent; required for Instagram Login deliveries."""
    token = client.cipher().decrypt(connection.encrypted_token.encode()).decode()
    client.graph(
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


def usable(row):
    return bool(row and row.active and row.encrypted_token and (not row.expires_at or row.expires_at > now()))


def active_connections(workspace_id):
    rows = (
        InstagramConnection.query.filter_by(workspace_id=workspace_id, active=True)
        .order_by(InstagramConnection.created_at, InstagramConnection.id)
        .all()
    )
    return [row for row in rows if usable(row)]


def active_connection(workspace_id, connection_id=None):
    """The requested account, or the oldest usable one when none is named (single-account callers)."""
    query = InstagramConnection.query.filter_by(workspace_id=workspace_id, active=True)
    if connection_id:
        row = query.filter_by(id=str(connection_id)).first()
    else:
        row = next(iter(active_connections(workspace_id)), None)
    if not usable(row):
        raise APIError('Reconecte o Instagram desta conta.', 409)
    return row


def thread_connection(thread):
    """The account that owns an Instagram conversation (its address is `<instagram_id>:<peer>`)."""
    row = InstagramConnection.query.filter_by(
        workspace_id=thread.workspace_id, instagram_id=(thread.address or '').split(':')[0], active=True
    ).first()
    if not usable(row):
        raise APIError('Reconecte o Instagram que recebeu esta conversa.', 409)
    return row


def token(connection):
    return client.cipher().decrypt(connection.encrypted_token.encode()).decode()
