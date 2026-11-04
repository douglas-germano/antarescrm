from uuid import uuid4

import pytest
from app.extensions import db
from app.models import AuditLog, Company, Contact, InboxThread, Opportunity, StageHistory, WhatsAppConversation


def thread(d, channel='whatsapp', contact=None):
    values = {'workspace_id': d['ws'].id, 'contact_id': contact.id if contact else None}
    row = (
        WhatsAppConversation(**values, phone='5565999900001', contact_name='Pessoa da conversa')
        if channel == 'whatsapp'
        else InboxThread(
            **values, channel=channel, address='person@example.test' if channel == 'email' else 'provider-person'
        )
    )
    db.session.add(row)
    db.session.commit()
    return row


def create(client, d, row, body=None, user=None):
    source = 'whatsapp' if isinstance(row, WhatsAppConversation) else 'inbox'
    data = {
        'idempotency_key': str(uuid4()),
        'title': 'Negócio da conversa',
        'stage_id': d['stage'].id,
        'amount': '1250.00',
        'owner_id': d['member'].id,
    }
    data.update(body or {})
    return client.post(
        f'/api/v1/inbox/{source}/{row.id}/opportunities', headers=d['headers'](user or d['owner']), json=data
    )


@pytest.mark.parametrize('channel', ['whatsapp', 'instagram', 'email', 'sms'])
def test_create_from_linked_contact_preserves_company_and_stage_history(env, channel):
    client, d = env
    company = Company(workspace_id=d['ws'].id, name='Empresa')
    db.session.add(company)
    db.session.flush()
    contact = Contact(workspace_id=d['ws'].id, name='Cliente', company_id=company.id)
    db.session.add(contact)
    db.session.commit()
    row = thread(d, channel, contact)
    result = create(client, d, row, user=d['member'])
    assert result.status_code == 201, result.json
    deal = Opportunity.query.one()
    assert deal.contact_id == contact.id and deal.company_id == company.id
    assert deal.owner_id == d['member'].id and deal.status == 'open' and str(deal.amount) == '1250.00'
    history = StageHistory.query.one()
    assert history.opportunity_id == deal.id and history.user_id == d['member'].id
    assert result.json['conversation']['id'] == row.id
    assert AuditLog.query.filter_by(action='inbox_create_opportunity', resource_id=deal.id).count() == 1


def test_unlinked_thread_can_choose_existing_contact_and_retry_without_duplicate(env):
    client, d = env
    contact = Contact(workspace_id=d['ws'].id, name='Cliente existente')
    db.session.add(contact)
    db.session.commit()
    row = thread(d)
    body = {'contact_id': contact.id, 'idempotency_key': str(uuid4())}
    first, second = create(client, d, row, body), create(client, d, row, body)
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json['opportunity']['id'] == second.json['opportunity']['id'] == body['idempotency_key']
    assert Opportunity.query.count() == StageHistory.query.count() == 1
    assert db.session.get(WhatsAppConversation, row.id).contact_id == contact.id
    assert create(client, d, row, {**body, 'title': 'Outra intenção'}).status_code == 409


def test_new_contact_and_deal_created_atomically_and_replayed_safely(env):
    client, d = env
    row = thread(d, 'instagram')
    body = {
        'idempotency_key': str(uuid4()),
        'contact': {'name': 'Novo contato', 'email': 'new@example.test', 'phone': None},
    }
    first, second = create(client, d, row, body), create(client, d, row, body)
    assert first.status_code == 201 and second.status_code == 200
    contact = Contact.query.one()
    assert contact.source == 'Instagram' and contact.owner_id == d['member'].id
    assert Opportunity.query.one().contact_id == row.contact_id == contact.id
    assert StageHistory.query.count() == 1


def test_invalid_stage_rolls_back_contact_and_conversation_link(env):
    client, d = env
    row = thread(d)
    result = create(client, d, row, {'stage_id': d['other_stage'].id, 'contact': {'name': 'Não gravar'}})
    assert result.status_code == 404
    assert Contact.query.count() == Opportunity.query.count() == StageHistory.query.count() == 0
    assert db.session.get(WhatsAppConversation, row.id).contact_id is None


@pytest.mark.parametrize(
    'invalid', ['missing', 'archived', 'foreign_contact', 'foreign_owner', 'changed_contact', 'both_contacts']
)
def test_invalid_or_out_of_scope_reference_cannot_create_deal(env, invalid):
    client, d = env
    contact = Contact(workspace_id=d['ws'].id, name='Local', archived=invalid == 'archived')
    foreign = Contact(workspace_id=d['other'].id, name='Privado')
    another = Contact(workspace_id=d['ws'].id, name='Outro contato')
    db.session.add_all([contact, foreign, another])
    db.session.commit()
    row = thread(d, contact=contact if invalid in ('changed_contact', 'both_contacts') else None)
    body, status = {}, 422
    if invalid == 'archived':
        body['contact_id'] = contact.id
        status = 400
    if invalid == 'foreign_contact':
        body['contact_id'] = foreign.id
        status = 404
    if invalid == 'foreign_owner':
        body.update(contact_id=contact.id, owner_id=d['outsider'].id)
        status = 404
    if invalid == 'changed_contact':
        body['contact_id'] = another.id
        status = 409
    if invalid == 'both_contacts':
        body['contact'] = {'name': 'Não criar'}
    result = create(client, d, row, body)
    assert result.status_code == status, result.json
    assert Contact.query.count() == 3 and Opportunity.query.count() == 0


def test_thread_scope_auth_and_request_validation(env):
    client, d = env
    contact = Contact(workspace_id=d['ws'].id, name='Local')
    db.session.add(contact)
    db.session.commit()
    row = thread(d, contact=contact)
    assert create(client, d, row, user=d['outsider']).status_code == 404
    assert create(client, d, row, {'amount': '-1'}).status_code == 422
    assert create(client, d, row, {'contact': {'name': 'Invalid', 'email': 'wrong'}}).status_code == 422
    assert client.post(f'/api/v1/inbox/whatsapp/{row.id}/opportunities', json={}).status_code == 401
    assert (
        client.post(f'/api/v1/inbox/invalid/{row.id}/opportunities', headers=d['headers'](), json={}).status_code == 404
    )
    assert Opportunity.query.count() == 0
