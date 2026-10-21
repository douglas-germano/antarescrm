"""Covers modules extracted during the clean-code refactor: services, error handling and app factory."""

from decimal import Decimal
from uuid import uuid4

import pytest
from test_growth import env  # noqa: F401  (shared fixture)

from app import create_app
from app.extensions import db
from app.models import Contact, Opportunity, PipelineStage, StageHistory


def make_deal(d, amount='100.00', contact=True):
    person = Contact(workspace_id=d['ws'].id, name='Maria', email='maria@example.com')
    db.session.add(person)
    db.session.flush()
    deal = Opportunity(
        workspace_id=d['ws'].id,
        title='Proposta',
        stage_id=d['stage'].id,
        contact_id=person.id if contact else None,
        amount=Decimal(amount),
    )
    db.session.add(deal)
    db.session.commit()
    return deal


# ---------- opportunities service ----------
def test_close_requires_loss_reason_and_positive_amount(env):
    client, d = env
    deal = make_deal(d, amount='0')
    url = f'/api/v1/opportunities/{deal.id}/close'
    assert client.post(url, headers=d['headers'](), json={'status': 'lost'}).status_code == 400
    assert client.post(url, headers=d['headers'](), json={'status': 'won'}).status_code == 400
    assert client.post(url, headers=d['headers'](), json={'status': 'lost', 'loss_reason': 'Preço'}).status_code == 200
    assert db.session.get(Opportunity, deal.id).status == 'lost'


def test_closed_deal_cannot_be_closed_or_edited_again(env):
    client, d = env
    deal = make_deal(d)
    url = f'/api/v1/opportunities/{deal.id}'
    assert client.post(url + '/close', headers=d['headers'](), json={'status': 'won'}).status_code == 200
    assert client.post(url + '/close', headers=d['headers'](), json={'status': 'won'}).status_code == 409
    assert client.patch(url, headers=d['headers'](), json={'title': 'Novo'}).status_code == 409


def test_stage_change_records_history(env):
    client, d = env
    second = PipelineStage(workspace_id=d['ws'].id, name='Proposta', position=1)
    db.session.add(second)
    deal = make_deal(d)
    response = client.patch(f'/api/v1/opportunities/{deal.id}', headers=d['headers'](), json={'stage_id': second.id})
    assert response.status_code == 200
    history = StageHistory.query.filter_by(opportunity_id=deal.id).one()
    assert (history.from_stage_id, history.to_stage_id) == (d['stage'].id, second.id)
    detail = client.get(f'/api/v1/opportunities/{deal.id}', headers=d['headers']()).json
    assert len(detail['history']) == 1


def test_create_inherits_company_and_ignores_other_workspace_stage(env):
    client, d = env
    deal = make_deal(d)
    response = client.post(
        '/api/v1/opportunities',
        headers=d['headers'](),
        json={'title': 'Outro', 'stage_id': d['other_stage'].id, 'contact_id': deal.contact_id},
    )
    assert response.status_code == 404


# ---------- rule validation service ----------
@pytest.mark.parametrize(
    'action',
    [
        {'kind': 'send_message'},
        {'kind': 'add_tag'},
        {'kind': 'move_stage'},
        {'kind': 'reply_comment'},
        {'kind': 'create_task'},
    ],
)
def test_rule_actions_are_validated(env, action):
    client, d = env
    body = {'name': 'Regra', 'event': 'form.submitted', 'task_title': 'Retornar', 'actions': [action]}
    response = client.post('/api/v1/automations', headers=d['headers'](), json=body)
    assert response.status_code == 422, response.json


# ---------- public form submission service ----------
def test_repeating_submission_key_is_idempotent(env):
    client, d = env
    body = {
        'submission_key': str(uuid4()),
        'name': 'Lead',
        'email': 'lead@example.com',
        'phone': '65999999999',
        'consent': True,
    }
    url = f'/api/v1/public/forms/{d["form"].id}/submit'
    assert client.post(url, json=body).status_code == 200
    assert client.post(url, json=body).status_code == 200
    assert Contact.query.count() == Opportunity.query.count() == 1


# ---------- error handling and factory ----------
def test_error_envelope_for_validation_and_missing_records(env):
    client, d = env
    invalid = client.post('/api/v1/opportunities', headers=d['headers'](), json={})
    assert invalid.status_code == 422 and invalid.json['error']['code'] == 'validation_error'
    missing = client.get(f'/api/v1/opportunities/{uuid4()}', headers=d['headers']())
    assert missing.status_code == 404 and 'message' in missing.json['error']


def test_requests_without_token_get_a_json_401(env):
    client, _ = env
    response = client.get('/api/v1/opportunities')
    assert response.status_code == 401 and response.json['error']['code'] == 'unauthorized'


def test_security_headers_are_applied(env):
    client, _ = env
    response = client.get('/api/v1/health')
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['Cache-Control'] == 'no-store'


def test_production_rejects_weak_secrets_and_sqlite(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    strong = 'x' * 40
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        create_app(
            {'SECRET_KEY': 'development-secret', 'JWT_SECRET_KEY': strong, 'SQLALCHEMY_DATABASE_URI': 'sqlite://'}
        )
    with pytest.raises(RuntimeError, match='PostgreSQL'):
        create_app({'SECRET_KEY': strong, 'JWT_SECRET_KEY': strong, 'SQLALCHEMY_DATABASE_URI': 'sqlite://'})


def test_split_packages_keep_public_import_paths():
    from app.models import Contact, Workspace  # noqa: F401
    from app.routes.crm import fold
    from app.schemas import CompanySchema, StrictSchema  # noqa: F401
    from app.schemas.growth import CONSENT

    assert fold('João') == 'joao' and CONSENT


# ---------- tasks and companies ----------
def test_task_lifecycle_filters_and_completion(env):
    client, d = env
    headers = d['headers']()
    created = client.post('/api/v1/tasks', headers=headers, json={'title': 'Ligar', 'priority': 'high'})
    assert created.status_code == 201 and created.json['assignee_id'] == d['owner'].id
    task_id = created.json['id']
    done = client.patch(f'/api/v1/tasks/{task_id}', headers=headers, json={'status': 'done'})
    assert done.status_code == 200 and done.json['status'] == 'done'
    listed = client.get('/api/v1/tasks?status=done&mine=true&search=lig', headers=headers).json
    assert [item['id'] for item in listed['items']] == [task_id]
    assert client.delete(f'/api/v1/tasks/{task_id}', headers=headers).status_code == 204
    assert client.get('/api/v1/tasks', headers=headers).json['total'] == 0


def test_company_archive_and_workspace_isolation(env):
    client, d = env
    headers = d['headers']()
    company = client.post('/api/v1/companies', headers=headers, json={'name': 'Acme'})
    assert company.status_code == 201
    url = '/api/v1/companies/' + company.json['id']
    assert client.patch(url, headers=headers, json={'industry': 'Varejo'}).json['industry'] == 'Varejo'
    outsider = d['headers'](d['outsider'])
    assert client.get(url, headers=outsider).status_code == 404
    archived = client.delete(url, headers=headers)
    assert archived.status_code == 200 and archived.json['archived'] is True
    assert client.get('/api/v1/companies', headers=headers).json['total'] == 0
