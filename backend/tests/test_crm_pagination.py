from datetime import timedelta

from app.extensions import db
from app.models import Contact, Opportunity, PipelineStage, Task, now


def test_filtered_deal_pages_keep_global_summary_and_scope(env):
    client, d = env
    d['stage'].probability = 50
    other = PipelineStage(workspace_id=d['other'].id, name='Other', position=0)
    db.session.add(other)
    db.session.flush()
    for index in range(31):
        contact = Contact(workspace_id=d['ws'].id, name=f'Cliente {index:02}', phone='5566999990000', source='Site')
        db.session.add(contact)
        db.session.flush()
        db.session.add(
            Opportunity(
                workspace_id=d['ws'].id,
                stage_id=d['stage'].id,
                contact_id=contact.id,
                title=f'Negócio {index:02}',
                amount=100,
                created_at=now() - timedelta(days=index),
            )
        )
    db.session.add(Opportunity(workspace_id=d['other'].id, stage_id=other.id, title='Hidden', amount=9999))
    db.session.commit()
    response = client.get('/api/v1/opportunities?per_page=10&page=2&sort=title&direction=asc', headers=d['headers']())
    assert response.status_code == 200
    body = response.json
    assert len(body['items']) == 10 and body['total'] == 31 and body['pages'] == 4
    assert body['items'][0]['title'] == 'Negócio 10' and body['items'][0]['contact_name'] == 'Cliente 10'
    assert body['summary']['amount'] == '3100.00' and body['summary']['weighted'] == '1550.00'
    assert body['summary']['stages'][d['stage'].id]['count'] == 31
    found = client.get('/api/v1/opportunities?search=Cliente+30&source=Site', headers=d['headers']()).json
    assert found['total'] == 1 and found['summary']['amount'] == '100.00'
    stale = client.get('/api/v1/opportunities?sort=stale&direction=desc&per_page=1', headers=d['headers']())
    assert stale.status_code == 200 and stale.json['items'][0]['title'] == 'Negócio 30'
    assert client.get('/api/v1/opportunities?min_amount=NaN', headers=d['headers']()).status_code == 422


def test_contacts_and_tasks_filter_before_paginating(env):
    client, d = env
    for index in range(30):
        contact = Contact(workspace_id=d['ws'].id, name=f'Contato {index:02}', source='Evento', owner_id=d['owner'].id)
        db.session.add(contact)
        db.session.flush()
        db.session.add(
            Task(
                workspace_id=d['ws'].id,
                contact_id=contact.id,
                title=f'Tarefa {index:02}',
                status='done' if index == 29 else 'todo',
                assignee_id=d['owner'].id,
            )
        )
    db.session.commit()
    contacts = client.get('/api/v1/contacts?per_page=10&page=3&source=Evento', headers=d['headers']()).json
    assert contacts['total'] == 30 and len(contacts['items']) == 10 and contacts['sources'] == ['Evento']
    tasks = client.get('/api/v1/tasks?view=closed&search=Contato+29', headers=d['headers']()).json
    assert tasks['total'] == 1 and tasks['items'][0]['contact_name'] == 'Contato 29'
    assert tasks['items'][0]['assignee_name'] == d['owner'].name
    assert client.get('/api/v1/tasks?view=closed', headers=d['headers'](d['outsider'])).json['total'] == 0


def test_contact_search_preserves_company_tags_and_custom_fields(env):
    from app.models import Company

    client, d = env
    company = Company(workspace_id=d['ws'].id, name='Metal Norte')
    db.session.add(company)
    db.session.flush()
    contact = Contact(
        workspace_id=d['ws'].id,
        company_id=company.id,
        name='Maria Souza',
        tags=['vip'],
        custom_fields={'cidade': 'Cuiaba'},
    )
    db.session.add(contact)
    db.session.commit()
    for term in ('Metal', 'vip', 'Cuiaba', 'Maria Norte'):
        result = client.get('/api/v1/contacts', query_string={'search': term}, headers=d['headers']())
        assert result.status_code == 200 and result.json['total'] == 1
