import json
from datetime import timedelta

from app.extensions import db
from app.models import ApiToken, AuditLog, InboxMessage, InboxThread, InstagramComment, InstagramPost, now
from app.services import api_tokens
from app.services.instagram import client as instagram_client
from helpers.instagram import configure_instagram, event, receive

ALL = sorted(api_tokens.TOKEN_SCOPES)
PUBLISH = 'instagram_business_basic,instagram_business_content_publish,instagram_business_manage_insights'


def token(client, d, scopes=ALL, user=None, days=90):
    response = client.post(
        '/api/v1/api-tokens',
        headers=d['headers'](user) if user else d['headers'](),
        json={'name': 'Claude', 'scopes': scopes, 'days': days},
    )
    assert response.status_code == 201, response.json
    return response.json['token']


def rpc(client, secret, method, params=None, identifier=1, headers=None):
    body = {'jsonrpc': '2.0', 'method': method, **({'id': identifier} if identifier is not None else {})}
    if params is not None:
        body['params'] = params
    return client.post('/api/v1/mcp', json=body, headers={'Authorization': 'Bearer ' + secret, **(headers or {})})


def call(client, secret, name, arguments=None):
    response = rpc(client, secret, 'tools/call', {'name': name, 'arguments': arguments or {}})
    assert response.status_code == 200, response.data
    result = response.json['result']
    return result, json.loads(result['content'][0]['text'])


def test_tokens_are_shown_once_hashed_scoped_and_revocable(env):
    client, d = env
    assert client.post('/api/v1/api-tokens', headers=d['headers'](d['member']), json={}).status_code == 403
    assert (
        client.post('/api/v1/api-tokens', headers=d['headers'](), json={'name': 'x', 'scopes': ['root']}).status_code
        == 422
    )
    secret = token(client, d, ['messages:read'])
    assert secret.startswith('antares_')
    row = ApiToken.query.one()
    assert row.token_hash != secret and secret not in json.dumps(row.to_dict(), default=str)
    listing = client.get('/api/v1/api-tokens', headers=d['headers']()).json
    assert listing['endpoint'].endswith('/mcp') and 'token' not in listing['items'][0]
    assert 'token_hash' not in listing['items'][0]
    assert client.get('/api/v1/api-tokens', headers=d['headers'](d['outsider'])).json['items'] == []
    assert rpc(client, secret, 'ping').json['result'] == {}
    assert client.delete(f'/api/v1/api-tokens/{row.id}', headers=d['headers']()).json['active'] is False
    response = rpc(client, secret, 'ping')
    assert response.status_code == 401 and 'Bearer' in response.headers['WWW-Authenticate']


def test_protocol_handshake_lists_only_permitted_tools_and_rejects_bad_requests(env):
    client, d = env
    secret = token(client, d, ['messages:read'])
    init = rpc(
        client, secret, 'initialize', {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 't'}}
    )
    result = init.json['result']
    assert result['protocolVersion'] == '2025-06-18' and result['capabilities']['tools'] == {'listChanged': False}
    assert result['serverInfo']['name'] == 'antares-crm' and 'confirm=true' in result['instructions']
    assert (
        rpc(client, secret, 'initialize', {'protocolVersion': '1999-01-01'}).json['result']['protocolVersion']
        == '2025-06-18'
    )
    assert rpc(client, secret, 'notifications/initialized', identifier=None).status_code == 202
    names = {t['name'] for t in rpc(client, secret, 'tools/list').json['result']['tools']}
    assert names == {'get_account', 'list_conversations', 'read_conversation'}
    denied = rpc(client, secret, 'tools/call', {'name': 'send_message', 'arguments': {}}).json
    assert denied['error']['code'] == -32602
    assert rpc(client, secret, 'resources/list').json['error']['code'] == -32601
    assert (
        client.post('/api/v1/mcp', json={'nope': 1}, headers={'Authorization': 'Bearer ' + secret}).status_code == 400
    )
    assert rpc(client, secret, 'ping', headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.post('/api/v1/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}).status_code == 401
    assert client.get('/api/v1/mcp').status_code == 405
    _, account = call(client, secret, 'get_account')
    assert account['account'] == d['ws'].name and account['scopes'] == ['messages:read']


def test_expired_tokens_and_creators_without_access_are_refused(env):
    client, d = env
    secret = token(client, d, ['messages:read'])
    row = ApiToken.query.one()
    row.expires_at = now() - timedelta(seconds=1)
    db.session.commit()
    assert rpc(client, secret, 'ping').status_code == 401
    row.expires_at = now() + timedelta(days=1)
    d['owner'].active = False
    db.session.commit()
    assert rpc(client, secret, 'ping').status_code == 401


def test_reads_and_sends_instagram_messages_with_confirmation_and_idempotency(env, monkeypatch):
    client, d = env
    configure_instagram(client, d)
    receive(client, event())
    secret = token(client, d)
    _, listing = call(client, secret, 'list_conversations', {'channel': 'instagram'})
    conversation = listing['conversations'][0]
    assert conversation['source'] == 'inbox' and conversation['channel'] == 'instagram'
    _, thread = call(
        client, secret, 'read_conversation', {'conversation_id': conversation['conversation_id'], 'source': 'inbox'}
    )
    assert thread['messages'][0]['text'] == 'Hello' and thread['reply_window_open'] is True
    sent = []
    monkeypatch.setattr(
        instagram_client, 'graph', lambda path, token, **kw: sent.append(kw['json']) or {'message_id': 'm1'}
    )
    args = {
        'conversation_id': conversation['conversation_id'],
        'source': 'inbox',
        'text': 'Oi!',
        'idempotency_key': 'k1',
    }
    result, data = call(client, secret, 'send_message', args)
    assert result['isError'] and 'confirm=true' in data['error'] and not sent
    for _ in range(2):
        result, data = call(client, secret, 'send_message', {**args, 'confirm': True})
        assert not result['isError'] and data['status'] == 'sent'
    assert len(sent) == 1 and InboxMessage.query.filter_by(direction='out').count() == 1
    assert AuditLog.query.filter_by(action='mcp.action.send_message').count() == 2
    other = token(client, d, ['messages:read'], user=d['outsider'])
    _, foreign = call(
        client, other, 'read_conversation', {'conversation_id': conversation['conversation_id'], 'source': 'inbox'}
    )
    assert foreign['status'] == 404


def test_hourly_budget_stops_irreversible_actions(env, monkeypatch):
    client, d = env
    configure_instagram(client, d)
    receive(client, event())
    secret = token(client, d)
    thread = InboxThread.query.one()
    monkeypatch.setattr(api_tokens, 'ACTIONS_PER_HOUR', 1)
    monkeypatch.setattr(instagram_client, 'graph', lambda *a, **k: {'message_id': 'x'})
    args = {'conversation_id': thread.id, 'source': 'inbox', 'text': 'Oi', 'confirm': True}
    assert not call(client, secret, 'send_message', args)[0]['isError']
    result, data = call(client, secret, 'send_message', {**args, 'text': 'De novo'})
    assert result['isError'] and data['status'] == 429


def test_posts_respect_draft_and_publish_scopes(env):
    client, d = env
    connection = configure_instagram(client, d)
    connection.scopes = PUBLISH
    db.session.commit()
    media = [{'url': 'https://cdn.example.com/a.jpg', 'kind': 'image'}]
    drafts = token(client, d, ['instagram:drafts', 'instagram:read'])
    base = {'account_id': connection.id, 'media_type': 'IMAGE', 'media': media, 'caption': 'Oi'}
    result, data = call(client, drafts, 'create_instagram_post', base)
    assert not result['isError'] and data['post']['status'] == 'draft'
    result, data = call(client, drafts, 'create_instagram_post', {**base, 'action': 'publish', 'confirm': True})
    assert result['isError'] and data['status'] == 403
    publisher = token(client, d, ['instagram:publish'])
    result, data = call(client, publisher, 'create_instagram_post', {**base, 'action': 'publish'})
    assert result['isError'] and 'confirm=true' in data['error']
    later = (now() + timedelta(days=1)).isoformat()
    result, data = call(
        client,
        publisher,
        'create_instagram_post',
        {**base, 'action': 'schedule', 'scheduled_at': later, 'confirm': True},
    )
    assert not result['isError'] and data['post']['status'] == 'scheduled'
    assert InstagramPost.query.count() == 2
    _, posts = call(client, drafts, 'list_instagram_posts', {'account_id': connection.id})
    assert {p['status'] for p in posts['posts']} == {'draft', 'scheduled'}


def test_comments_are_listed_live_and_answered_once(env, monkeypatch):
    client, d = env
    connection = configure_instagram(client, d)
    secret = token(client, d)
    calls = []

    def graph(path, token, method='GET', detail=False, **kwargs):
        calls.append((method, path, kwargs.get('params') or {}, kwargs.get('json')))
        if path == '1234/media':
            return {'data': [{'id': 'm1', 'caption': 'Promo', 'comments_count': 2, 'permalink': 'https://ig/p/1'}]}
        if path == 'm1/comments':
            return {
                'data': [
                    {'id': '501', 'text': 'Quanto custa?', 'username': 'ana', 'timestamp': '2026-11-11T10:00:00+0000'},
                    {
                        'id': '502',
                        'text': 'Amei',
                        'username': 'bia',
                        'timestamp': '2026-11-11T09:00:00+0000',
                        'replies': {'data': [{'username': 'testprofile', 'text': 'Obrigado!'}]},
                    },
                ]
            }
        if path == '501':
            return {
                'id': '501',
                'text': 'Quanto custa?',
                'from': {'id': '9001', 'username': 'ana'},
                'media': {'id': 'm1'},
            }
        if path == '501/replies':
            return {'id': '601'}
        if path == '1234/messages':
            return {'message_id': 'dm1'}
        raise AssertionError(path)

    monkeypatch.setattr(instagram_client, 'graph', graph)
    _, listing = call(client, secret, 'list_instagram_comments', {'account_id': connection.id, 'unanswered_only': True})
    assert [c['comment_id'] for c in listing['comments']] == ['501']
    reply = {'account_id': connection.id, 'comment_id': '501', 'text': 'R$ 50', 'confirm': True}
    result, data = call(client, secret, 'reply_instagram_comment', reply)
    assert not result['isError'] and data['replied']
    assert ('POST', '501/replies', {'message': 'R$ 50'}, None) in calls
    result, data = call(client, secret, 'reply_instagram_comment', reply)
    assert result['isError'] and data['status'] == 409
    result, data = call(
        client, secret, 'reply_instagram_comment', {**reply, 'private': True, 'text': 'Te chamei no direct'}
    )
    assert not result['isError']
    row = InstagramComment.query.one()
    assert row.replied_at and row.private_replied_at and row.username == 'ana'
    _, listing = call(client, secret, 'list_instagram_comments', {'account_id': connection.id})
    assert all(c['replied_publicly'] for c in listing['comments'])
