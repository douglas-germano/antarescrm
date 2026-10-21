import hashlib
import hmac
import json
import time
from uuid import uuid4
from test_growth import env
from app.extensions import db
from app.models import Contact, InboxMessage, InboxThread, MessageTemplate, WhatsAppConversation, WhatsAppConnection
from app.services.communications import dispatch, enqueue


def setup_channel(client, d):
    client.application.config['COMMUNICATION_ACCOUNTS'] = {d['ws'].id: {'email': {'host': 'smtp.example.test', 'from_address': 'agency@example.test', 'inbound_secret': 'test-inbound-secret'}}}
    contact = Contact(workspace_id=d['ws'].id, name='Lead', email='lead@example.test', phone='+5565999999999')
    template = MessageTemplate(workspace_id=d['ws'].id, name='Hello', channel='email', subject='Hello {{name}}', content='Welcome {{name}}')
    db.session.add_all([contact, template]); db.session.commit()
    return contact, template


def test_broadcast_is_scoped_atomic_and_idempotent(env, monkeypatch):
    client, d = env; contact, template = setup_channel(client, d); h = d['headers']()
    outsider = Contact(workspace_id=d['other'].id, name='Private', email='other@example.test')
    db.session.add(outsider); db.session.commit()
    body = {'contact_ids': [contact.id, outsider.id], 'template_id': template.id, 'idempotency_key': str(uuid4())}
    assert client.post('/api/v1/communications/broadcasts', headers=h, json=body).status_code == 404
    assert InboxMessage.query.count() == 0
    body['contact_ids'] = [contact.id, contact.id]
    for _ in range(2):
        response = client.post('/api/v1/communications/broadcasts', headers=h, json=body)
        assert response.status_code == 202 and response.json['total'] == 1
    assert InboxMessage.query.count() == 1 and InboxMessage.query.one().content == 'Welcome Lead'
    assert client.post('/api/v1/communications/broadcasts', headers=d['headers'](d['member']), json=body).status_code == 403
    assert client.post('/api/v1/communications/broadcasts', headers=d['headers'](d['outsider']), json=body).status_code == 404
    assert client.get('/api/v1/inbox', headers=d['headers'](d['outsider'])).json['items'] == []
    thread = InboxThread.query.one()
    assert client.get(f'/api/v1/inbox/inbox/{thread.id}/messages', headers=d['headers'](d['outsider'])).status_code == 404
    calls = []
    monkeypatch.setattr('app.services.communications.deliver', lambda t, m: calls.append(m.id) or 'provider-1')
    assert len(dispatch(d['ws'].id)) == 1 and len(dispatch(d['ws'].id)) == 0 and len(calls) == 1
    assert InboxMessage.query.one().status == 'sent'


def test_ambiguous_send_never_retried_and_config_not_exposed(env, monkeypatch):
    client, d = env; contact, template = setup_channel(client, d)
    row = enqueue(d['ws'].id, contact, 'email', 'hello', 'subject', str(uuid4()), d['owner'].id); db.session.commit()
    def failure(*args): raise TimeoutError('secret-provider-response')
    monkeypatch.setattr('app.services.communications.deliver', failure)
    dispatch(d['ws'].id)
    assert row.status == 'unknown' and 'secret' not in row.error
    assert dispatch(d['ws'].id) == []
    assert client.post(f'/api/v1/communications/messages/{row.id}/resume', headers=d['headers'](), json={}).status_code == 409
    response = client.get('/api/v1/communications/channels', headers=d['headers']())
    assert 'smtp.example.test' not in response.get_data(as_text=True) and 'test-inbound-secret' not in response.get_data(as_text=True)


def test_signed_receive_replay_and_account_isolation(env):
    client, d = env; contact, _ = setup_channel(client, d)
    raw = json.dumps({'provider_id': 'provider-1', 'address': contact.email, 'content': 'Hello back', 'subject': 'Reply'})
    timestamp = str(int(time.time()))
    signature = hmac.new(b'test-inbound-secret', (timestamp + '.' + raw).encode(), hashlib.sha256).hexdigest()
    path = f"/api/v1/communications/receive/{d['ws'].id}/email"
    headers = {'Content-Type': 'application/json', 'X-Timestamp': timestamp, 'X-Signature': signature}
    assert client.post(path, data=raw).status_code == 401
    assert client.post(path, data=raw, headers=headers).status_code == 201
    assert client.post(path, data=raw, headers=headers).status_code == 200
    assert InboxMessage.query.count() == 1 and InboxThread.query.one().contact_id == contact.id
    assert client.post(f"/api/v1/communications/receive/{d['other'].id}/email", data=raw, headers=headers).status_code == 404
    headers['X-Timestamp'] = '1'
    assert client.post(path, data=raw, headers=headers).status_code == 401


def test_native_whatsapp_is_visible_and_isolated(env):
    client, d = env
    thread = WhatsAppConversation(workspace_id=d['ws'].id, phone='5565999999999', contact_name='WhatsApp Lead')
    db.session.add(thread); db.session.commit()
    response = client.get('/api/v1/inbox', headers=d['headers']())
    assert response.json['items'][0]['source'] == 'whatsapp'
    assert client.get(f'/api/v1/inbox/whatsapp/{thread.id}/messages', headers=d['headers'](d['outsider'])).status_code == 404


def test_worker_blocks_missing_provider_and_cancels_revoked_sender(env):
    client, d = env; contact, _ = setup_channel(client, d)
    first = enqueue(d['ws'].id, contact, 'sms', 'hello', '', str(uuid4()), d['owner'].id)
    db.session.commit(); dispatch(d['ws'].id)
    assert first.status == 'blocked'
    second = enqueue(d['ws'].id, contact, 'email', 'hello', '', str(uuid4()), d['owner'].id)
    db.session.commit(); d['owner'].active = False; db.session.commit(); dispatch(d['ws'].id)
    assert second.status == 'cancelled'
