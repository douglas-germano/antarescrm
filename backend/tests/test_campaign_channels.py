from unittest.mock import Mock

import pytest
from test_growth import env

from app.extensions import db
from app.models import (
    CampaignRecipient,
    CommunicationSuppression,
    Contact,
    InboxMessage,
    MessageTemplate,
    WhatsAppConnection,
)
from app.services import communications


@pytest.fixture(autouse=True)
def no_real_delivery(monkeypatch):
    monkeypatch.setattr(communications, 'deliver', Mock(side_effect=AssertionError('Unexpected provider call')))


def seed(d, **values):
    row = Contact(workspace_id=values.pop('workspace_id', d['ws'].id), name=values.pop('name', 'Cliente'), **values)
    db.session.add(row)
    db.session.commit()
    return row


def connected(d):
    row = WhatsAppConnection(
        workspace_id=d['ws'].id, instance_name='fixture', webhook_secret='fixture-secret', state='open'
    )
    db.session.add(row)
    db.session.commit()
    return row


def create(client, d, **values):
    body = {'name': 'WhatsApp clientes', 'channel': 'whatsapp', 'content': 'Olá {{name}}', 'audience': {}}
    body.update(values)
    result = client.post('/api/v1/campaigns', headers=d['headers'](), json=body)
    assert result.status_code == 201, result.json
    return result.json


def action(client, d, row, verb, body=None):
    return client.post(f'/api/v1/campaigns/{row["id"]}/{verb}', headers=d['headers'](), json=body or {})


def prepared(client, d, count=1):
    connected(d)
    for i in range(count):
        seed(d, name=f'Cliente {i}', phone=f'+55659999000{i:02}')
    row = create(client, d)
    result = action(client, d, row, 'prepare')
    assert result.status_code == 200, result.json
    assert result.json['status'] == 'ready'
    return result.json


def queued(client, d, count=1):
    row = prepared(client, d, count)
    result = action(client, d, row, 'send', {'audience_hash': row['audience_hash'], 'consent_confirmed': True})
    assert result.status_code == 200, result.json
    assert result.json['metrics']['queued'] == count
    return result.json


def test_whatsapp_audience_filters_deduplicates_and_excludes_blocked_aliases(env):
    client, d = env
    seed(d, phone='+55 (65) 99990-0001', tags=['VIP'], source='Site')
    seed(d, phone='5565999900001', tags=['VIP'], source='Site')
    blocked = seed(d, phone='+5565999900002', tags=['VIP'], source='Site')
    seed(d, phone='5565999900002', tags=['VIP'], source='Site')
    seed(d, tags=['VIP'], source='Site')
    seed(d, phone='inválido', tags=['VIP'], source='Site')
    seed(d, phone='+5565999900003', tags=['Outro'], source='Site')
    seed(d, phone='+5565999900004', tags=['VIP'], source='Outro')
    seed(d, phone='+5565999900005', tags=['VIP'], source='Site', archived=True)
    seed(d, phone='+5565999900006', workspace_id=d['other'].id, tags=['VIP'], source='Site')
    db.session.add(CommunicationSuppression(workspace_id=d['ws'].id, contact_id=blocked.id, channel='whatsapp'))
    db.session.commit()
    result = client.post(
        '/api/v1/campaigns/audience',
        headers=d['headers'](),
        json={'channel': 'whatsapp', 'tag': 'VIP', 'source': 'Site'},
    )
    assert result.status_code == 200
    assert result.json['total'] == 1 and result.json['limit'] == 100
    assert result.json['excluded'] == {'without_phone': 1, 'invalid': 1, 'suppressed': 2, 'duplicates': 1}
    assert result.json['sample'][0]['phone'] == '+5565999900001'


def test_whatsapp_campaign_full_flow_is_scoped_and_idempotent(env, monkeypatch):
    client, d = env
    unrelated = seed(d, phone='+5565999999999')
    other = communications.enqueue(d['ws'].id, unrelated, 'whatsapp', 'Outro envio', '', 'unrelated', d['owner'].id)
    unrelated_id = other.id
    unrelated.archived = True
    db.session.commit()
    row = queued(client, d, 2)
    recipients = CampaignRecipient.query.filter_by(campaign_id=row['id']).all()
    assert len(recipients) == 2 and all(r.email is None for r in recipients)
    assert InboxMessage.query.filter(InboxMessage.content.like('Olá Cliente%')).count() == 2
    again = action(client, d, row, 'send', {'audience_hash': row['audience_hash'], 'consent_confirmed': True})
    assert again.json['metrics']['queued'] == 2 and InboxMessage.query.count() == 3
    deliver = Mock(return_value='provider-id')
    monkeypatch.setattr(communications, 'deliver', deliver)
    result = action(client, d, row, 'process')
    assert result.json['metrics']['sent'] == 1 and result.json['metrics']['queued'] == 1
    assert db.session.get(InboxMessage, unrelated_id).status == 'queued'
    assert deliver.call_count == 1
    result = action(client, d, row, 'process')
    assert result.json['status'] == 'sent' and result.json['metrics']['sent'] == 2
    action(client, d, row, 'process')
    assert deliver.call_count == 2
    listing = client.get('/api/v1/campaigns', headers=d['headers']()).json
    assert listing['items'][0]['channel'] == 'whatsapp' and listing['items'][0]['status'] == 'sent'


def test_ambiguous_delivery_is_not_retried(env, monkeypatch):
    client, d = env
    row = queued(client, d)
    deliver = Mock(side_effect=TimeoutError('private-provider-token'))
    monkeypatch.setattr(communications, 'deliver', deliver)
    result = action(client, d, row, 'process')
    assert result.json['status'] == 'unknown' and result.json['metrics']['unknown'] == 1
    assert 'private-provider-token' not in result.get_data(as_text=True)
    action(client, d, row, 'process')
    assert deliver.call_count == 1


@pytest.mark.parametrize('change', ['phone', 'suppression', 'role', 'archived', 'duplicate_suppression'])
def test_queued_campaign_rechecks_permissions_and_address_before_delivery(env, change):
    client, d = env
    row = queued(client, d)
    recipient = CampaignRecipient.query.filter_by(campaign_id=row['id']).one()
    contact = db.session.get(Contact, recipient.contact_id)
    if change == 'phone':
        contact.phone = '+5565999999999'
    if change == 'role':
        d['owner'].role = 'member'
    if change == 'archived':
        contact.archived = True
    if change in ('suppression', 'duplicate_suppression'):
        blocked = seed(d, phone=contact.phone) if change == 'duplicate_suppression' else contact
        db.session.add(CommunicationSuppression(workspace_id=d['ws'].id, contact_id=blocked.id, channel='whatsapp'))
    db.session.commit()
    communications.dispatch(d['ws'].id, message_ids=[recipient.message_id])
    assert db.session.get(InboxMessage, recipient.message_id).status == 'cancelled'
    communications.deliver.assert_not_called()


def test_changed_prepared_audience_blocks_send(env):
    client, d = env
    row = prepared(client, d)
    seed(d, phone='+5565999999999')
    result = action(client, d, row, 'send', {'audience_hash': row['audience_hash'], 'consent_confirmed': True})
    assert result.status_code == 409 and InboxMessage.query.count() == 0


def test_campaign_requires_consent_connection_and_bounded_audience(env):
    client, d = env
    row = create(client, d)
    assert action(client, d, row, 'prepare').status_code == 409
    connected(d)
    assert action(client, d, row, 'prepare').status_code == 422
    for i in range(101):
        seed(d, phone=f'+5565999900{i:03}')
    assert action(client, d, row, 'prepare').status_code == 422
    assert CampaignRecipient.query.count() == 0
    assert action(client, d, row, 'send', {'audience_hash': '0' * 64, 'consent_confirmed': False}).status_code == 422
    assert action(client, d, row, 'process').status_code == 409


def test_campaign_and_template_permissions_and_channel_immutability(env):
    client, d = env
    row = create(client, d)
    assert (
        client.patch(
            '/api/v1/campaigns/' + row['id'], headers=d['headers'](), json={'channel': 'email', 'subject': 'Subject'}
        ).status_code
        == 409
    )
    for who, status in [('member', 403), ('outsider', 404)]:
        assert (
            client.post(f'/api/v1/campaigns/{row["id"]}/prepare', headers=d['headers'](d[who]), json={}).status_code
            == status
        )
    for channel in ('email', 'whatsapp'):
        body = {
            'name': 'Modelo ' + channel,
            'channel': channel,
            'subject': 'Assunto' if channel == 'email' else '',
            'content': 'Mensagem reutilizável',
        }
        result = client.post('/api/v1/message-templates', headers=d['headers'](), json=body)
        assert result.status_code == 201
        identifier = result.json['id']
        assert (
            client.patch(
                '/api/v1/message-templates/' + identifier,
                headers=d['headers'](d['outsider']),
                json={'content': 'Outro'},
            ).status_code
            == 404
        )
        assert (
            client.patch(
                '/api/v1/message-templates/' + identifier, headers=d['headers'](), json={'content': 'Editado'}
            ).json['content']
            == 'Editado'
        )
    assert MessageTemplate.query.count() == 2
    assert (
        client.post('/api/v1/campaigns', headers=d['headers'](), json={'name': 'Email', 'content': 'Hello'}).status_code
        == 422
    )
