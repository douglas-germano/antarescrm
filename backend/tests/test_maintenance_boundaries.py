import io
import json
import logging
from uuid import uuid4

import pytest
from app.common import APIError
from app.contracts import build_spec
from app.extensions import db
from app.models import InboxThread
from app.observability import StructuredFormatter
from app.services import communications, delivery_transactions, inbox, whatsapp
from app.tenancy import AccountContext
from helpers.whatsapp import arrange


def test_whatsapp_routes_share_delivery_and_idempotency(env, monkeypatch):
    client, data = env
    _, conversation, gateway = arrange(data, monkeypatch)
    body = {'content': 'Resposta', 'idempotency_key': str(uuid4())}
    first = client.post(
        f'/api/v1/whatsapp/conversations/{conversation.id}/messages', headers=data['headers'](), json=body
    )
    second = client.post(f'/api/v1/inbox/whatsapp/{conversation.id}/messages', headers=data['headers'](), json=body)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json['id'] == second.json['id']
    gateway.send_text.assert_called_once()
    key = str(uuid4())
    file = client.post(
        f'/api/v1/inbox/whatsapp/{conversation.id}/messages',
        headers=data['headers'](),
        data={
            'idempotency_key': key,
            'file': (io.BytesIO(b'fake-pdf'), 'anexo.pdf', 'application/pdf'),
        },
    )
    assert file.status_code == 201
    gateway.send_media.assert_called_once()
    outside = client.post(
        f'/api/v1/inbox/whatsapp/{conversation.id}/messages', headers=data['headers'](data['outsider']), json=body
    )
    assert outside.status_code == 404


def test_explicit_account_context_is_scoped_without_a_request(env):
    _, data = env
    own = InboxThread(workspace_id=data['ws'].id, channel='email', address='own@example.test')
    other = InboxThread(workspace_id=data['other'].id, channel='email', address='other@example.test')
    db.session.add_all([own, other])
    db.session.commit()
    account = AccountContext(data['ws'].id, data['owner'].id)
    assert [row['id'] for row in inbox.list_threads(account)['items']] == [own.id]
    with pytest.raises(APIError) as denied:
        account.get(InboxThread, other.id)
    assert denied.value.status == 404
    with pytest.raises(ValueError):
        AccountContext('', data['owner'].id)


def test_provider_is_never_called_when_durable_claim_fails(env, monkeypatch):
    _, data = env
    connection, conversation, gateway = arrange(data, monkeypatch)

    def fail():
        raise RuntimeError('claim storage failed')

    monkeypatch.setattr(delivery_transactions.db.session, 'commit', fail)
    with pytest.raises(RuntimeError):
        whatsapp.send_outgoing(connection, conversation, 'Hello', str(uuid4()))
    gateway.send_text.assert_not_called()
    db.session.rollback()


def test_inbox_email_reply_only_queues_and_validates_the_contact(env, monkeypatch):
    from app.models import Contact, InboxMessage

    client, data = env
    contact = Contact(workspace_id=data['ws'].id, name='Cliente', email='client@example.test')
    db.session.add(contact)
    db.session.flush()
    thread = InboxThread(workspace_id=data['ws'].id, channel='email', address=contact.email, contact_id=contact.id)
    db.session.add(thread)
    db.session.commit()
    monkeypatch.setattr(communications, 'available', lambda *args: True)
    response = client.post(
        f'/api/v1/inbox/inbox/{thread.id}/messages',
        headers=data['headers'](),
        json={'content': 'Resposta', 'idempotency_key': str(uuid4())},
    )
    assert response.status_code == 202
    assert db.session.get(InboxMessage, response.json['id']).status == 'queued'
    thread.contact_id = None
    db.session.commit()
    response = client.post(
        f'/api/v1/inbox/inbox/{thread.id}/messages',
        headers=data['headers'](),
        json={'content': 'Resposta', 'idempotency_key': str(uuid4())},
    )
    assert response.status_code == 422


def test_logs_correlate_requests_without_query_secrets(env, caplog):
    client, data = env
    with caplog.at_level(logging.INFO, logger='app'):
        response = client.get(
            '/api/v1/tasks?access_token=secret-query-value',
            headers={**data['headers'](), 'X-Request-ID': 'test.operation-123'},
        )
    assert response.status_code == 200
    assert response.headers['X-Request-ID'] == 'test.operation-123'
    records = [record for record in caplog.records if record.getMessage() == 'http_request_completed']
    assert records[-1].event_fields['workspace_id'] == data['ws'].id
    assert records[-1].event_fields['request_id'] == 'test.operation-123'
    assert 'secret-query-value' not in '\n'.join(StructuredFormatter().format(record) for record in records)


def test_unexpected_error_logs_stack_locations_without_exception_secrets(env, caplog):
    client, _ = env

    def fail():
        raise RuntimeError('private-provider-token')

    client.application.add_url_rule('/test-unexpected-error', view_func=fail)
    response = client.get('/test-unexpected-error', headers={'X-Request-ID': 'unsafe request id'})
    assert response.status_code == 500
    assert len(response.headers['X-Request-ID']) == 32
    record = next(record for record in caplog.records if record.exc_info)
    formatted = StructuredFormatter().format(record)
    assert 'private-provider-token' not in formatted
    assert json.loads(formatted)['error_type'] == 'RuntimeError'
    assert json.loads(formatted)['stack']


def test_generated_contracts_keep_validation_pagination_and_public_response_types(env):
    client, _ = env
    spec = build_spec(client.application)
    components = spec['components']['schemas']
    assert 'name' in components['ContactInput']['required']
    assert 'name' not in components['ContactPatchInput'].get('required', [])
    assert components['OpportunityRecord']['properties']['amount']['type'] == 'string'
    assert components['ContactRecord']['properties']['company_id']['nullable'] is True
    stage = spec['paths']['/pipeline/stages']['get']['responses']['2XX']['content']['application/json']['schema']
    assert stage['required'] == ['items']
    assert spec['paths']['/contacts']['get']['security'] == [{'bearerAuth': []}]
    operations = [operation['operationId'] for methods in spec['paths'].values() for operation in methods.values()]
    assert len(operations) == len(set(operations))
