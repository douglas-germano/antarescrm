"""Instagram events: webhook deduplication and dispatch."""

import hashlib
import json

from ...common import APIError
from ...extensions import db
from ...models import InstagramConnection, InstagramEvent, Workspace
from . import comments, messages


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
        comments.process_comment(connection, item.get('value') or {})
        return
    if kind != 'messaging':
        return  # Other subscribed events retained, never silently discarded.
    messages.ingest_message(connection, item, key)


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
