"""Instagram connections: account connection and webhook subscription."""

from datetime import timedelta

from flask import current_app

from ...common import APIError
from ...extensions import db
from ...models import InstagramConnection, InstagramEvent, now
from . import client, profiles

SUBSCRIBED_FIELDS = 'messages'


def connect(workspace_id, token, expires_in=None):
    data = client.profile(token)
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
    row.username, row.encrypted_token, row.active = (
        data['username'],
        client.cipher().encrypt(token.encode()).decode(),
        True,
    )
    row.expires_at = now() + timedelta(seconds=int(expires_in)) if expires_in else None
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


def active_connection(workspace_id):
    row = InstagramConnection.query.filter_by(workspace_id=workspace_id, active=True).first()
    if not row or (row.expires_at and row.expires_at <= now()):
        raise APIError('Reconecte o Instagram desta conta.', 409)
    return row
