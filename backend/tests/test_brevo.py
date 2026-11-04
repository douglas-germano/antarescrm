import hashlib
import re
from datetime import timedelta
from unittest.mock import Mock

import pytest
from app.common import APIError
from app.extensions import db
from app.models import (
    BrevoConnection,
    BrevoEvent,
    CampaignRecipient,
    CommunicationSuppression,
    Contact,
    EmailCampaign,
    User,
    UserAccessToken,
    now,
)
from app.services import access_email, brevo
from werkzeug.security import check_password_hash


@pytest.fixture(autouse=True)
def isolated_provider(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('No real provider calls in tests')

    monkeypatch.setattr(brevo.requests, 'request', forbidden)


def configure(client, data, monkeypatch):
    client.application.config.update(
        APP_URL='https://crm.example.test',
        BREVO_SYSTEM_API_KEY=None,
        BREVO_SYSTEM_SENDER_EMAIL=None,
        BREVO_ENCRYPTION_KEY=None,
    )
    calls = []

    def api(key, path, method='GET', **kwargs):
        calls.append((path, method, kwargs))
        if path == 'account':
            return {}
        if path == 'senders':
            return {'senders': [{'email': 'sender@example.com', 'active': True}]}
        if path == 'smtp/email':
            return {'messageId': 'transactional-id'}
        if path == 'webhooks':
            return {'id': 51}
        if path == 'contacts/folders':
            return {'id': 11}
        if path == 'contacts/lists':
            return {'id': 22}
        if path == 'contacts/import':
            return {'processId': 33}
        if path == 'processes/33':
            return {'status': 'completed'}
        if path == 'contacts/lists/22/contacts/add':
            return {'contacts': {'success': []}}
        if path == 'emailCampaigns' and method == 'POST':
            return {'id': 44}
        if path == 'emailCampaigns/44/sendNow':
            return {}
        if path == 'emailCampaigns/44':
            return {'status': 'sent'}
        if path == 'webhooks/51' and method == 'PUT':
            return {}
        raise AssertionError((path, method))

    monkeypatch.setattr(brevo, 'api', api)
    body = {
        'api_key': 'private-api-key-not-for-browser',
        'sender_email': 'sender@example.com',
        'sender_name': 'Antares',
    }
    result = client.post('/api/v1/brevo/connection', headers=data['headers'](), json=body)
    assert result.status_code == 200
    return calls


def contact(data, **kwargs):
    row = Contact(workspace_id=data['ws'].id, name=kwargs.pop('name', 'Lead'), **kwargs)
    db.session.add(row)
    db.session.commit()
    return row


def draft(client, data, **kwargs):
    body = {'name': 'News', 'subject': 'Novidades', 'content': 'Olá\nUma oferta <segura>', 'audience': {}}
    body.update(kwargs)
    result = client.post('/api/v1/campaigns', headers=data['headers'](), json=body)
    assert result.status_code == 201, result.json
    return result.json


def action(client, data, row, verb, body=None):
    return client.post(f'/api/v1/campaigns/{row["id"]}/{verb}', headers=data['headers'](), json=body or {})


def ready_campaign(client, data, monkeypatch):
    calls = configure(client, data, monkeypatch)
    client.post('/api/v1/brevo/webhooks', headers=data['headers'](), json={})
    person = contact(data, email='lead@example.com', tags=['Newsletter'])
    row = draft(client, data, audience={'tag': 'Newsletter'})
    assert action(client, data, row, 'prepare').json['status'] == 'importing'
    result = action(client, data, row, 'refresh')
    assert result.json['status'] == 'ready', result.json
    return result.json, person, calls


def test_connection_private_validated_scoped_and_can_disconnect(env, monkeypatch):
    client, data = env
    calls = configure(client, data, monkeypatch)
    assert [item[0] for item in calls] == ['account', 'senders']
    row = BrevoConnection.query.one()
    assert row.encrypted_key != 'private-api-key-not-for-browser'
    assert brevo.key_for(row) == 'private-api-key-not-for-browser'
    for path in ['/brevo/connection', '/campaigns']:
        assert client.get('/api/v1' + path, headers=data['headers'](data['member'])).status_code == 403
    result = client.get('/api/v1/brevo/connection', headers=data['headers']()).get_data(as_text=True)
    assert 'private-api-key' not in result and 'encrypted_key' not in result and 'webhook_secret' not in result
    assert client.get('/api/v1/brevo/connection', headers=data['headers'](data['outsider'])).json['connection'] is None
    assert client.post('/api/v1/brevo/webhooks', headers=data['headers'](), json={}).json['webhook_id'] == 51
    assert client.post('/api/v1/brevo/webhooks', headers=data['headers'](), json={}).status_code == 200
    assert client.delete('/api/v1/brevo/connection', headers=data['headers']()).status_code == 204
    assert not row.active and not row.encrypted_key
    assert client.post('/api/v1/brevo/webhooks', headers=data['headers'](), json={}).status_code == 409


def test_reject_missing_key_or_unverified_sender(env, monkeypatch):
    client, data = env
    body = {'sender_email': 'sender@example.com', 'sender_name': 'Sender'}
    assert client.post('/api/v1/brevo/connection', headers=data['headers'](), json=body).status_code == 422
    monkeypatch.setattr(brevo, 'api', lambda key, path: {'senders': []})
    body['api_key'] = 'not-a-real-provider-key'
    assert client.post('/api/v1/brevo/connection', headers=data['headers'](), json=body).status_code == 422
    assert BrevoConnection.query.count() == 0


def test_rotation_cannot_send_existing_campaign_with_other_credentials(env, monkeypatch):
    client, data = env
    row, _, _ = ready_campaign(client, data, monkeypatch)
    connection = BrevoConnection.query.one()
    old_secret = connection.webhook_secret
    result = client.post(
        '/api/v1/brevo/connection',
        headers=data['headers'](),
        json={'api_key': 'another-private-api-key', 'sender_email': 'sender@example.com', 'sender_name': 'Sender'},
    )
    assert result.status_code == 200 and connection.version == 2 and connection.webhook_secret != old_secret
    assert (
        action(
            client, data, row, 'send', {'audience_hash': row['audience_hash'], 'consent_confirmed': True}
        ).status_code
        == 409
    )


def test_access_reset_generic_short_lived_once_and_revokes_sessions(env, monkeypatch):
    client, data = env
    calls = configure(client, data, monkeypatch)
    headers = data['headers']()
    existing = client.post('/api/v1/auth/forgot-password', json={'slug': data['ws'].slug, 'email': data['owner'].email})
    missing = client.post('/api/v1/auth/forgot-password', json={'slug': 'missing', 'email': 'missing@example.com'})
    assert existing.status_code == missing.status_code == 200 and existing.json == missing.json
    row = UserAccessToken.query.one()
    assert row.delivery_status == 'sent' and row.expires_at < now() + timedelta(minutes=31)
    sent = next(item for item in calls if item[0] == 'smtp/email')
    token = re.search(r'#token=([\w-]+)', sent[2]['json']['textContent']).group(1)
    assert token not in str(row.__dict__) and row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    client.post('/api/v1/auth/forgot-password', json={'slug': data['ws'].slug, 'email': data['owner'].email})
    assert len([item for item in calls if item[0] == 'smtp/email']) == 1
    assert client.post('/api/v1/auth/accept-access', json={'token': token, 'password': 'short'}).status_code == 422
    body = {'token': token, 'password': 'a-new-password-123'}
    assert client.post('/api/v1/auth/accept-access', json=body).status_code == 200
    assert check_password_hash(data['owner'].password_hash, body['password'])
    assert client.get('/api/v1/auth/me', headers=headers).status_code == 401
    assert client.post('/api/v1/auth/accept-access', json=body).status_code == 422
    assert (
        client.post('/api/v1/auth/accept-access', json={'token': 'x' * 43, 'password': body['password']}).status_code
        == 422
    )


@pytest.mark.parametrize('invalidate', ['expired', 'version', 'email', 'inactive', 'workspace'])
def test_reset_cannot_accept_invalid_or_revoked_identity(env, monkeypatch, invalidate):
    client, data = env
    calls = configure(client, data, monkeypatch)
    access_email.issue(data['owner'], 'reset')
    row = UserAccessToken.query.one()
    token = re.search(
        r'#token=([\w-]+)', next(item for item in calls if item[0] == 'smtp/email')[2]['json']['textContent']
    ).group(1)
    if invalidate == 'expired':
        row.expires_at = now() - timedelta(seconds=1)
    if invalidate == 'version':
        data['owner'].token_version += 1
    if invalidate == 'email':
        data['owner'].email = 'changed@example.com'
    if invalidate == 'inactive':
        data['owner'].active = False
    if invalidate == 'workspace':
        data['ws'].active = False
    db.session.commit()
    assert (
        client.post('/api/v1/auth/accept-access', json={'token': token, 'password': 'a-new-password-123'}).status_code
        == 422
    )


def test_access_not_configured_and_ambiguous_send_stay_generic(env, monkeypatch):
    client, data = env
    client.application.config.update(BREVO_SYSTEM_API_KEY=None)
    body = {'slug': data['ws'].slug, 'email': data['owner'].email}
    assert client.post('/api/v1/auth/forgot-password', json=body).status_code == 200
    assert UserAccessToken.query.count() == 0
    configure(client, data, monkeypatch)
    monkeypatch.setattr(brevo, 'send_access', Mock(side_effect=TimeoutError()))
    assert client.post('/api/v1/auth/forgot-password', json=body).status_code == 200
    assert UserAccessToken.query.one().delivery_status == 'unknown'


def test_invite_inactive_until_accepted_and_role_is_scoped(env, monkeypatch):
    client, data = env
    calls = configure(client, data, monkeypatch)
    body = {'name': 'New teammate', 'email': 'new@example.com', 'role': 'member'}
    assert (
        client.post('/api/v1/users/invitations', headers=data['headers'](data['member']), json=body).status_code == 403
    )
    result = client.post('/api/v1/users/invitations', headers=data['headers'](), json=body)
    assert result.status_code == 201 and result.json['delivery_status'] == 'sent'
    user = User.query.filter_by(email='new@example.com').one()
    assert not user.active and user.workspace_id == data['ws'].id
    listed = client.get('/api/v1/users', headers=data['headers']()).json['items']
    assert next(item for item in listed if item['id'] == user.id)['invite_pending']
    token = re.search(
        r'#token=([\w-]+)', next(item for item in calls if item[0] == 'smtp/email')[2]['json']['textContent']
    ).group(1)
    assert (
        client.post('/api/v1/auth/accept-access', json={'token': token, 'password': 'new-user-password'}).status_code
        == 200
    )
    assert user.active and user.role == 'member'
    assert client.post('/api/v1/users/invitations', headers=data['headers'](), json=body).status_code == 409
    assert (
        client.post('/api/v1/users/invitations', headers=data['headers'](), json={**body, 'role': 'owner'}).status_code
        == 422
    )


def test_platform_sender_only_for_access_and_transactional_confirmation_required(env, monkeypatch):
    client, data = env
    client.application.config.update(
        BREVO_SYSTEM_API_KEY='platform-key',
        BREVO_SYSTEM_SENDER_EMAIL='system@example.com',
        BREVO_SYSTEM_SENDER_NAME='Antares',
    )
    assert brevo.access_sender(data['ws'].id)[0] == 'platform-key'
    with pytest.raises(APIError):
        brevo.connection(data['ws'].id)
    monkeypatch.setattr(brevo, 'api', lambda *args, **kwargs: {})
    with pytest.raises(APIError):
        brevo.send_access(data['ws'].id, 'to@example.com', 'Name', 'Subject', 'Body')


def test_tags_and_has_email_are_dynamic_and_saved_views_work(env):
    client, data = env
    row = contact(data, email='lead@example.com', tags=['Cliente'])
    contact(data, email=None, tags=['Cliente VIP'])
    contact(data, email='   ', tags=[])
    for param, total in [('has_email=true', 1), ('has_email=false', 2), ('tag=Cliente', 1), ('tag=Cliente+VIP', 1)]:
        result = client.get('/api/v1/contacts?' + param, headers=data['headers']())
        assert result.status_code == 200 and result.json['total'] == total, result.json
    assert client.get('/api/v1/contacts', headers=data['headers']()).json['tags'] == ['Cliente', 'Cliente VIP']
    result = client.post(
        '/api/v1/contact-views',
        headers=data['headers'](),
        json={'name': 'Com e-mail', 'filters': {'email': 'true', 'tag': 'Cliente'}},
    )
    assert result.status_code == 201 and result.json['filters']['email'] == 'true'
    row.email = None
    db.session.commit()
    assert client.get('/api/v1/contacts?has_email=true', headers=data['headers']()).json['total'] == 0


def test_audience_excludes_invalid_duplicate_archived_and_suppressed_and_other_tenant(env):
    client, data = env
    contact(data, email='LEAD@example.com', tags=['Newsletter'])
    contact(data, email='lead@example.com', tags=['Newsletter'])
    contact(data, email='bad', tags=['Newsletter'])
    contact(data, email=None, tags=['Newsletter'])
    blocked = contact(data, email='blocked@example.com', tags=['Newsletter'])
    contact(data, email='BLOCKED@example.com', tags=['Newsletter'])
    contact(data, email='archived@example.com', tags=['Newsletter'], archived=True)
    db.session.add(Contact(workspace_id=data['other'].id, name='Other', email='other@example.com', tags=['Newsletter']))
    db.session.add(CommunicationSuppression(workspace_id=data['ws'].id, contact_id=blocked.id, channel='email'))
    db.session.commit()
    result = client.post('/api/v1/campaigns/audience', headers=data['headers'](), json={'tag': 'Newsletter'})
    assert result.json['total'] == 1 and result.json['sample'][0]['email'] == 'lead@example.com'
    assert result.json['excluded'] == {'without_email': 1, 'invalid': 1, 'suppressed': 2, 'duplicates': 1}
    assert (
        client.post('/api/v1/campaigns/audience', headers=data['headers'](), json={'source': 'None'}).json['total'] == 0
    )


def test_campaign_draft_prepare_refresh_send_once_and_webhook_metrics(env, monkeypatch):
    client, data = env
    row, person, calls = ready_campaign(client, data, monkeypatch)
    assert not any(item[0].endswith('sendNow') for item in calls)
    imported = next(item[2]['json'] for item in calls if item[0] == 'contacts/import')
    assert imported['updateExistingContacts'] is False and 'emailBlacklist' not in imported
    remote = next(item[2]['json'] for item in calls if item[0] == 'emailCampaigns')
    assert '&lt;segura&gt;' in remote['htmlContent'] and '{{ unsubscribe }}' in remote['htmlContent']
    assert (
        action(
            client, data, row, 'send', {'audience_hash': row['audience_hash'], 'consent_confirmed': False}
        ).status_code
        == 422
    )
    for _ in range(2):
        assert (
            action(
                client, data, row, 'send', {'audience_hash': row['audience_hash'], 'consent_confirmed': True}
            ).status_code
            == 200
        )
    assert len([item for item in calls if item[0].endswith('sendNow')]) == 1
    connection = BrevoConnection.query.one()
    path = '/api/v1/brevo/webhook/' + connection.id
    payload = {'camp_id': 44, 'email': person.email, 'event': 'delivered', 'ts_event': 123}
    assert client.post(path, json=payload).status_code == 401
    for kind in ['opened', 'delivered', 'unsubscribed', 'unsubscribed']:
        payload['event'] = kind
        assert client.post(path, json=payload, headers={'X-Brevo-Secret': connection.webhook_secret}).status_code == 200
    assert BrevoEvent.query.count() == 3 and CommunicationSuppression.query.count() == 1
    recipient = CampaignRecipient.query.one()
    assert recipient.status == 'unsubscribed' and recipient.events['delivered']
    result = client.get('/api/v1/campaigns', headers=data['headers']()).json['items'][0]
    assert result['metrics']['unsubscribed'] == result['metrics']['delivered'] == 1
    assert client.get('/api/v1/campaigns', headers=data['headers'](data['outsider'])).json['items'] == []
    assert (
        client.post(
            f'/api/v1/campaigns/{row["id"]}/send', headers=data['headers'](data['outsider']), json={}
        ).status_code
        == 404
    )


@pytest.mark.parametrize('change', ['archive', 'email', 'suppression', 'tag', 'hash'])
def test_changed_campaign_audience_cannot_be_sent(env, monkeypatch, change):
    client, data = env
    row, person, calls = ready_campaign(client, data, monkeypatch)
    if change == 'archive':
        person.archived = True
    if change == 'email':
        person.email = 'changed@example.com'
    if change == 'tag':
        person.tags = []
    if change == 'suppression':
        db.session.add(CommunicationSuppression(workspace_id=data['ws'].id, contact_id=person.id, channel='email'))
    db.session.commit()
    result = action(
        client,
        data,
        row,
        'send',
        {'audience_hash': '0' * 64 if change == 'hash' else row['audience_hash'], 'consent_confirmed': True},
    )
    assert result.status_code == 409 and not any(item[0].endswith('sendNow') for item in calls)


@pytest.mark.parametrize('stage', ['prepare', 'refresh', 'send'])
def test_ambiguous_campaign_operations_never_repeat_automatically(env, monkeypatch, stage):
    client, data = env
    row, person, calls = ready_campaign(client, data, monkeypatch)
    if stage == 'prepare':
        row = draft(client, data)
    elif stage == 'refresh':
        saved = db.session.get(EmailCampaign, row['id'])
        saved.status = 'importing'
        saved.provider_id = None
        db.session.commit()
    original = brevo.api

    def failure(key, path, method='GET', **kwargs):
        if method == 'POST':
            raise TimeoutError()
        return original(key, path, method, **kwargs)

    monkeypatch.setattr(brevo, 'api', failure)
    result = action(
        client,
        data,
        row,
        stage,
        {'audience_hash': row['audience_hash'], 'consent_confirmed': True} if stage == 'send' else {},
    )
    assert result.status_code == 200 and result.json['status'] == 'unknown'
    if stage == 'send':
        assert (
            action(
                client, data, row, stage, {'audience_hash': row['audience_hash'], 'consent_confirmed': True}
            ).status_code
            == 409
        )
    assert action(client, data, row, 'prepare').json['status'] == 'unknown'


def test_provider_adapter_does_not_leak_errors_or_credentials(env, monkeypatch):
    client, _ = env
    response = Mock(ok=True, content=b'{}', status_code=401)
    response.json.return_value = {'ok': True}
    send = Mock(return_value=response)
    monkeypatch.setattr(brevo.requests, 'request', send)
    assert brevo.api('private-key', 'account') == {'ok': True}
    assert send.call_args.kwargs['headers']['api-key'] == 'private-key'
    response.ok = False
    with pytest.raises(APIError) as error:
        brevo.api('private-key', 'account')
    assert 'private-key' not in str(error.value.message)
    monkeypatch.setattr(brevo.requests, 'request', Mock(side_effect=brevo.requests.Timeout()))
    with pytest.raises(APIError):
        brevo.api('private-key', 'account')


@pytest.mark.parametrize(
    'status,message,expected_code,expected_status',
    [
        (401, 'Key not found private-key', 'brevo_invalid_key', 422),
        (401, 'We have detected you are using an unrecognised IP address private-key', 'brevo_ip_not_authorized', 422),
        (403, 'Your IP address is not authorized private-key', 'brevo_ip_not_authorized', 422),
        (403, 'Permission denied private-key', 'brevo_permission_denied', 422),
        (429, 'Too many requests private-key', 'brevo_rate_limited', 429),
        (402, 'Not enough credits private-key', 'brevo_request_rejected', 422),
        (400, 'Invalid request private-key', 'brevo_request_rejected', 422),
        (502, 'Bad gateway private-key', 'brevo_unavailable', 503),
    ],
)
def test_provider_rejection_is_actionable_without_secrets(
    env, monkeypatch, caplog, status, message, expected_code, expected_status
):
    client, data = env
    response = Mock(ok=False, content=b'{}', status_code=status)
    response.json.return_value = {'code': 'unauthorized', 'message': message}
    monkeypatch.setattr(brevo.requests, 'request', Mock(return_value=response))
    result = client.post(
        '/api/v1/brevo/connection',
        headers=data['headers'](),
        json={
            'api_key': 'private-key-value-used-only-in-tests',
            'sender_email': 'sender@example.com',
            'sender_name': 'Antares',
        },
    )
    assert result.status_code == expected_status and result.json['error']['code'] == expected_code
    assert 'private-key' not in result.get_data(as_text=True) and 'private-key' not in caplog.text
    assert BrevoConnection.query.count() == 0


def test_key_paste_trims_outer_whitespace_and_rejects_internal_whitespace(env, monkeypatch):
    client, data = env
    configure(client, data, monkeypatch)
    body = {
        'api_key': '  private-api-key-not-for-browser\n',
        'sender_email': 'sender@example.com',
        'sender_name': 'Antares',
    }
    assert client.post('/api/v1/brevo/connection', headers=data['headers'](), json=body).status_code == 200
    assert brevo.key_for(BrevoConnection.query.one()) == 'private-api-key-not-for-browser'
    for key in ('Bearer private-key-value', 'invalid\nkey-value-more-than-twenty', 'á-private-key-with-enough-chars'):
        body['api_key'] = key
        assert client.post('/api/v1/brevo/connection', headers=data['headers'](), json=body).status_code == 422


@pytest.mark.parametrize('body', [[], 'invalid', None])
def test_invalid_provider_response_remains_bounded(env, monkeypatch, body):
    client, _ = env
    response = Mock(ok=True, content=b'nonempty', status_code=200)
    if body is None:
        response.json.side_effect = ValueError('private response')
    else:
        response.json.return_value = body
    monkeypatch.setattr(brevo.requests, 'request', Mock(return_value=response))
    with pytest.raises(APIError) as error:
        brevo.api('private-key', 'account')
    assert error.value.status == 503 and error.value.code == 'brevo_invalid_response'
