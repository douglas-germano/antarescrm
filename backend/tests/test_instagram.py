import hashlib
import hmac
import json
from datetime import timedelta
from urllib.parse import urlparse, parse_qs
from uuid import uuid4
from cryptography.fernet import Fernet
from test_growth import env
from app.extensions import db
from app.models import (
    InstagramConnection,
    InstagramEvent,
    InstagramOAuthState,
    InboxThread,
    InboxMessage,
    Contact,
    AutomationRule,
    AutomationRun,
    now,
)
from app.services import instagram as service


import pytest


@pytest.fixture(autouse=True)
def no_profile_lookup(monkeypatch):
    monkeypatch.setattr(
        service, 'fetch_profile', lambda connection, scoped_id: None
    )  # Never reach the network in tests.


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


def test_signed_receive_is_scoped_deduplicated_and_triggers_automation(env):
    client, d = env
    configure_instagram(client, d)
    db.session.add(
        AutomationRule(
            workspace_id=d['ws'].id,
            name='Incoming',
            event='message.received',
            active=True,
            task_title='Respond',
            due_days=0,
        )
    )
    db.session.commit()
    assert receive(client, event(), False).status_code == 401
    assert InboxMessage.query.count() == 0
    for _ in range(2):
        assert receive(client, event()).status_code == 200
    assert (
        InstagramEvent.query.count()
        == InboxMessage.query.count()
        == Contact.query.count()
        == AutomationRun.query.count()
        == 1
    )
    assert InboxThread.query.one().channel == 'instagram'
    assert client.get('/api/v1/inbox', headers=d['headers'](d['outsider'])).json['items'] == []
    assert client.get('/api/v1/instagram/connection', headers=d['headers'](d['member'])).status_code == 403
    body = client.get('/api/v1/instagram/connection', headers=d['headers']()).get_data(as_text=True)
    assert 'private-token' not in body and 'encrypted_token' not in body and 'test-secret' not in body


def test_non_message_events_are_durable_and_echoes_do_not_create_leads(env):
    client, d = env
    configure_instagram(client, d)
    body = event()
    body['entry'][0]['messaging'][0]['message']['is_echo'] = True
    body['entry'][0]['changes'] = [{'field': 'comments', 'value': {'id': 'comment1', 'text': 'Test'}}]
    assert receive(client, body).status_code == 200
    assert InstagramEvent.query.count() == 2 and Contact.query.count() == 0


def test_reply_window_is_enforced_and_failed_sends_never_retry(env, monkeypatch):
    client, d = env
    configure_instagram(client, d)
    assert receive(client, event(age=25)).status_code == 200
    thread = InboxThread.query.one()
    path = f'/api/v1/inbox/inbox/{thread.id}/messages'
    payload = {'content': 'Reply', 'idempotency_key': str(uuid4())}
    assert client.post(path, headers=d['headers'](), json=payload).status_code == 409
    assert receive(client, event('new-mid')).status_code == 200
    calls = []

    def timeout(*args, **kwargs):
        calls.append(args)
        raise TimeoutError('secret')

    monkeypatch.setattr(service, 'graph', timeout)
    for _ in range(2):
        result = client.post(path, headers=d['headers'](), json=payload)
        assert result.status_code == 200 and result.json['status'] == 'unknown'
    assert len(calls) == 1
    assert client.post(path, headers=d['headers'](d['outsider']), json=payload).status_code == 404


def test_successful_reply_keeps_recipient_and_idempotency(env, monkeypatch):
    client, d = env
    configure_instagram(client, d)
    receive(client, event())
    thread = InboxThread.query.one()
    calls = []

    def send(path, token, method, **kwargs):
        assert path == '1234/messages' and token == 'private-token' and method == 'POST'
        assert kwargs['json'] == {'recipient': {'id': '5678'}, 'message': {'text': 'Reply'}}
        calls.append(path)
        return {'message_id': 'out-1'}

    monkeypatch.setattr(service, 'graph', send)
    key = str(uuid4())
    path = f'/api/v1/inbox/inbox/{thread.id}/messages'
    for _ in range(2):
        result = client.post(path, headers=d['headers'](), json={'content': 'Reply', 'idempotency_key': key})
        assert result.status_code == 200 and result.json['status'] == 'sent'
    assert len(calls) == 1
    assert (
        client.post(path, headers=d['headers'](), json={'content': 'Changed', 'idempotency_key': key}).status_code
        == 409
    )


def test_oauth_state_bound_to_user_account_expiry_and_single_use(env, monkeypatch):
    client, d = env
    configure_instagram(client, d)
    response = client.post('/api/v1/instagram/connect', headers=d['headers'](), json={})
    state = parse_qs(urlparse(response.json['url']).query)['state'][0]
    assert state not in InstagramOAuthState.query.one().state_hash
    data = {'state': state, 'code': 'auth-code'}
    assert client.post('/api/v1/instagram/complete', headers=d['headers'](d['outsider']), json=data).status_code == 409
    monkeypatch.setattr(service, 'oauth_tokens', lambda code: {'access_token': 'new-token', 'expires_in': 5000})
    monkeypatch.setattr(service, 'profile', lambda token: {'user_id': '1234', 'username': 'updated'})
    response = client.post('/api/v1/instagram/complete', headers=d['headers'](), json=data)
    assert response.status_code == 200 and response.json['username'] == 'updated'
    assert 'encrypted_token' not in response.json
    assert client.post('/api/v1/instagram/complete', headers=d['headers'](), json=data).status_code == 409
    state = client.post('/api/v1/instagram/connect', headers=d['headers'](), json={}).json['url']
    row = InstagramOAuthState.query.order_by(InstagramOAuthState.created_at.desc()).first()
    row.expires_at = now() - timedelta(seconds=1)
    db.session.commit()
    assert (
        client.post(
            '/api/v1/instagram/complete',
            headers=d['headers'](),
            json={'state': parse_qs(urlparse(state).query)['state'][0], 'code': 'new'},
        ).status_code
        == 409
    )


def test_connection_cannot_cross_accounts_and_disconnect_keeps_history(env, monkeypatch):
    client, d = env
    configure_instagram(client, d)
    receive(client, event())
    monkeypatch.setattr(service, 'profile', lambda token: {'user_id': '1234', 'username': 'test'})
    from app.common import APIError
    import pytest

    with pytest.raises(APIError) as e:
        service.connect(d['other'].id, 'stolen')
    assert e.value.status == 409
    assert client.post('/api/v1/instagram/disconnect', headers=d['headers'](), json={}).status_code == 200
    row = InstagramConnection.query.one()
    assert not row.active and not row.encrypted_token
    assert InboxMessage.query.count() == 1


def test_connecting_subscribes_to_messages_and_failure_does_not_break_connection(env, monkeypatch):
    client, d = env
    configure_instagram(client, d)
    calls = []
    monkeypatch.setattr(service, 'oauth_tokens', lambda code: {'access_token': 'new-token', 'expires_in': 5000})
    monkeypatch.setattr(service, 'profile', lambda token: {'user_id': '1234', 'username': 'testprofile'})

    def graph(path, token, method='GET', **kwargs):
        calls.append((path, method, kwargs.get('params')))
        return {'success': True}

    monkeypatch.setattr(service, 'graph', graph)

    def finish():
        state = parse_qs(
            urlparse(client.post('/api/v1/instagram/connect', headers=d['headers'](), json={}).json['url']).query
        )['state'][0]
        return client.post('/api/v1/instagram/complete', headers=d['headers'](), json={'state': state, 'code': 'code'})

    ok = finish()
    assert ok.status_code == 200 and ok.json['subscribed'] is True and 'encrypted_token' not in ok.json
    assert calls == [('1234/subscribed_apps', 'POST', {'subscribed_fields': 'messages'})]
    from app.common import APIError

    def broken(*args, **kwargs):
        raise APIError('Recusado', 502)

    monkeypatch.setattr(service, 'graph', broken)
    again = finish()
    assert again.status_code == 200 and again.json['subscribed'] is False


def test_verify_reports_and_repairs_the_subscription(env, monkeypatch):
    client, d = env
    configure_instagram(client, d)
    receive(client, event())
    state = {'fields': []}

    def graph(path, token, method='GET', **kwargs):
        assert path == '1234/subscribed_apps'
        if method == 'POST':
            state['fields'] = ['messages']
            return {'success': True}
        return {'data': [{'id': 'test-id', 'subscribed_fields': state['fields']}] if state['fields'] else []}

    monkeypatch.setattr(service, 'graph', graph)
    result = client.post('/api/v1/instagram/verify', headers=d['headers'](), json={})
    assert result.status_code == 200
    assert (
        result.json['subscribed'] is True
        and result.json['activated'] is True
        and result.json['events'] == 1
        and result.json['last_event_at']
    )
    assert client.post('/api/v1/instagram/verify', headers=d['headers'](), json={}).json['activated'] is False
    assert client.post('/api/v1/instagram/verify', headers=d['headers'](d['member']), json={}).status_code == 403
    assert client.post('/api/v1/instagram/verify', headers=d['headers'](d['outsider']), json={}).status_code in (
        403,
        409,
    )


def test_new_contact_gets_name_and_username_from_the_instagram_profile(env, monkeypatch):
    client, d = env
    configure_instagram(client, d)
    monkeypatch.setattr(
        service, 'fetch_profile', lambda connection, scoped_id: {'name': 'Maria Souza', 'username': 'maria.souza'}
    )
    assert receive(client, event()).status_code == 200
    contact = Contact.query.one()
    assert contact.name == 'Maria Souza' and contact.custom_fields['instagram_username'] == 'maria.souza'
    assert contact.custom_fields['instagram_scoped_id'] == '5678'
    item = client.get('/api/v1/inbox', headers=d['headers']()).json['items'][0]
    assert item['display_address'] == '@maria.souza'


def test_username_is_used_when_the_profile_has_no_name_and_failures_keep_the_placeholder(env, monkeypatch):
    client, d = env
    configure_instagram(client, d)
    monkeypatch.setattr(service, 'fetch_profile', lambda connection, scoped_id: {'name': '', 'username': 'so.usuario'})
    receive(client, event('a'))
    assert Contact.query.one().name == '@so.usuario'
    Contact.query.delete()
    InboxMessage.query.delete()
    InboxThread.query.delete()
    db.session.commit()
    monkeypatch.setattr(service, 'fetch_profile', lambda connection, scoped_id: None)
    receive(client, event('b'))
    assert Contact.query.one().name == 'Instagram 5678'
    assert client.get('/api/v1/inbox', headers=d['headers']()).json['items'][0]['display_address'] == 'Instagram'


def test_placeholder_contacts_are_renamed_on_the_next_message_but_typed_names_are_kept(env, monkeypatch):
    client, d = env
    configure_instagram(client, d)
    receive(client, event('first'))
    assert Contact.query.one().name == 'Instagram 5678'
    monkeypatch.setattr(
        service, 'fetch_profile', lambda connection, scoped_id: {'name': 'Joana Lima', 'username': 'joana'}
    )
    receive(client, event('second'))
    contact = Contact.query.one()
    assert contact.name == 'Joana Lima'
    contact.name = 'Joana (cliente)'
    db.session.commit()
    monkeypatch.setattr(
        service, 'fetch_profile', lambda connection, scoped_id: {'name': 'Outro Nome', 'username': 'joana'}
    )
    receive(client, event('third'))
    assert Contact.query.one().name == 'Joana (cliente)'


# ---- comments as automation triggers ----
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


def test_comment_creates_contact_and_ignores_own_replies_and_duplicates(env):
    from app.models import InstagramComment

    client, d = env
    configure_instagram(client, d)
    assert receive(client, comment_event()).status_code == 200
    assert receive(client, comment_event()).status_code == 200  # webhook retry
    assert receive(client, comment_event('c2', sender='1234', username='testprofile')).status_code == 200  # own account
    assert receive(client, comment_event('c3', parent='c1')).status_code == 200  # reply, not a new comment
    assert InstagramComment.query.count() == 1
    contact = Contact.query.one()
    assert contact.name == '@cliente.ig' and contact.custom_fields['instagram_username'] == 'cliente.ig'
    assert InstagramComment.query.one().contact_id == contact.id


def test_dm_after_comment_reuses_the_same_contact(env):
    client, d = env
    configure_instagram(client, d)
    receive(client, comment_event(sender='5678'))
    receive(client, event())  # DM from the same person (5678)
    assert Contact.query.count() == 1


def test_keyword_condition_gates_the_rule(env):
    client, d = env
    configure_instagram(client, d)
    comment_rule(
        d,
        [{'kind': 'add_tag', 'tag': 'lead-ig', 'delay_minutes': 0}],
        {'mode': 'all', 'items': [{'field': 'comment.text', 'operator': 'contains', 'value': 'quero'}]},
    )
    receive(client, comment_event('a', 'Bonito demais'))
    assert AutomationRun.query.count() == 0
    receive(client, comment_event('b', 'EU QUERO saber mais', sender='9002', username='outra'))
    assert AutomationRun.query.count() == 1


def test_comment_actions_reply_publicly_and_by_private_message_once(env, monkeypatch):
    from app.models import InstagramComment
    from app.services.automations import process

    client, d = env
    configure_instagram(client, d)
    comment_rule(
        d,
        [
            {'kind': 'reply_comment', 'content': 'Obrigado, {{name}}! Te chamei no direct.', 'delay_minutes': 0},
            {'kind': 'private_reply', 'content': 'Oi {{username}}, aqui está o link.', 'delay_minutes': 0},
        ],
    )
    calls = []

    def graph(path, token, method='GET', **kwargs):
        calls.append((path, kwargs))
        return {'id': 'r1', 'message_id': 'dm1'}

    monkeypatch.setattr(service, 'graph', graph)
    receive(client, comment_event())
    process(d['ws'].id)
    assert [c[0] for c in calls] == ['c1/replies', '1234/messages']
    assert calls[0][1]['params'] == {'message': 'Obrigado, @cliente.ig! Te chamei no direct.'}
    assert calls[1][1]['json'] == {
        'recipient': {'comment_id': 'c1'},
        'message': {'text': 'Oi cliente.ig, aqui está o link.'},
    }
    row = InstagramComment.query.one()
    assert row.replied_at and row.private_replied_at
    assert AutomationRun.query.one().status == 'completed'
    assert InboxMessage.query.filter_by(direction='out').one().content.startswith('Oi cliente.ig')
    # Same comment again (e.g. a retried step) never answers twice.
    from app.models import AutomationJob

    for job in AutomationJob.query.all():
        job.status = 'pending'
    db.session.commit()
    process(d['ws'].id)
    assert len(calls) == 2


def test_hourly_limit_and_provider_failure_mark_the_step_failed(env, monkeypatch):
    from app.models import AutomationJob
    from app.services.automations import process
    from app.common import APIError

    client, d = env
    configure_instagram(client, d)
    comment_rule(d, [{'kind': 'reply_comment', 'content': 'Oi', 'delay_minutes': 0}])

    def refuse(*args, **kwargs):
        raise APIError('Recusado', 502)

    monkeypatch.setattr(service, 'graph', refuse)
    receive(client, comment_event())
    process(d['ws'].id)
    assert AutomationJob.query.one().status == 'failed'
    monkeypatch.setattr(service, 'COMMENT_REPLIES_PER_HOUR', 0)
    receive(client, comment_event('c9', sender='9009', username='z'))
    process(d['ws'].id)
    assert AutomationJob.query.filter_by(status='failed').count() == 2


def test_comment_action_validation(env):
    client, d = env
    base = {'name': 'x', 'event': 'instagram.comment', 'task_title': 't'}
    assert (
        client.post(
            '/api/v1/automations', json={**base, 'actions': [{'kind': 'reply_comment'}]}, headers=d['headers']()
        ).status_code
        == 422
    )
    assert (
        client.post(
            '/api/v1/automations',
            json={**base, 'actions': [{'kind': 'private_reply', 'content': 'á' * 600}]},
            headers=d['headers'](),
        ).status_code
        == 422
    )
    assert (
        client.post(
            '/api/v1/automations',
            json={**base, 'actions': [{'kind': 'reply_comment', 'content': 'Olá!'}]},
            headers=d['headers'](),
        ).status_code
        == 201
    )


def test_connection_card_shows_name_username_and_picture_and_refreshes_when_stale(env, monkeypatch):
    from datetime import timedelta as td

    client, d = env
    row = configure_instagram(client, d)
    calls = []

    def account(token):
        calls.append(token)
        return {
            'user_id': '1234',
            'username': 'novo.usuario',
            'name': 'Loja Exemplo',
            'profile_picture_url': 'https://cdn.example/foto.jpg',
        }

    monkeypatch.setattr(service, 'fetch_account', account)
    body = client.get('/api/v1/instagram/connection', headers=d['headers']()).json['connection']
    assert (
        body['name'] == 'Loja Exemplo'
        and body['username'] == 'novo.usuario'
        and body['profile_picture_url'] == 'https://cdn.example/foto.jpg'
    )
    assert 'encrypted_token' not in body and calls == ['private-token']
    client.get('/api/v1/instagram/connection', headers=d['headers']())
    assert len(calls) == 1  # fresh data is not fetched again
    db.session.get(InstagramConnection, row.id).profile_synced_at = now() - td(hours=7)
    db.session.commit()
    client.get('/api/v1/instagram/connection', headers=d['headers']())
    assert len(calls) == 2


def test_connection_card_survives_an_instagram_outage(env, monkeypatch):
    client, d = env
    configure_instagram(client, d)
    monkeypatch.setattr(service, 'fetch_account', lambda token: None)
    result = client.get('/api/v1/instagram/connection', headers=d['headers']())
    assert (
        result.status_code == 200
        and result.json['connection']['username'] == 'testprofile'
        and result.json['connection']['name'] is None
    )
