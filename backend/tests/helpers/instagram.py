import hashlib
import hmac
import json
from datetime import timedelta

from app.extensions import db
from app.models import InstagramConnection, now
from app.services import instagram as service
from cryptography.fernet import Fernet


def configure_instagram(client, d):
    client.application.config.update(
        INSTAGRAM_APP_ID='test-id',
        INSTAGRAM_APP_SECRET='test-secret',
        INSTAGRAM_ENCRYPTION_KEY=Fernet.generate_key().decode(),
    )
    row = InstagramConnection(
        workspace_id=d['ws'].id,
        instagram_id='1234',
        username='testprofile',
        encrypted_token=service.cipher().encrypt(b'private-token').decode(),
    )
    db.session.add(row)
    db.session.commit()
    return row


def event(mid='mid1', age=0):
    return {
        'object': 'instagram',
        'entry': [
            {
                'id': '1234',
                'messaging': [
                    {
                        'sender': {'id': '5678'},
                        'recipient': {'id': '1234'},
                        'timestamp': int((now() - timedelta(hours=age)).timestamp() * 1000),
                        'message': {'mid': mid, 'text': 'Hello'},
                    }
                ],
            }
        ],
    }


def receive(client, body, signature=True):
    raw = json.dumps(body).encode()
    return client.post(
        '/api/v1/instagram/webhook',
        data=raw,
        content_type='application/json',
        headers={
            'X-Hub-Signature-256': 'sha256=' + hmac.new(b'test-secret', raw, hashlib.sha256).hexdigest()
            if signature
            else 'sha256=invalid'
        },
    )


def comment_event(cid='c1', text='Eu quero!', sender='9001', username='cliente.ig', parent=None, media='m1'):
    value = {'id': cid, 'text': text, 'from': {'id': sender, 'username': username}, 'media': {'id': media}}
    if parent:
        value['parent_id'] = parent
    return {'object': 'instagram', 'entry': [{'id': '1234', 'changes': [{'field': 'comments', 'value': value}]}]}


def comment_rule(d, actions, conditions=None):
    from app.models import AutomationRule

    row = AutomationRule(
        workspace_id=d['ws'].id,
        name='Comentários',
        event='instagram.comment',
        task_title='t',
        active=True,
        actions=actions,
        conditions=conditions or {},
    )
    db.session.add(row)
    db.session.commit()
    return row
