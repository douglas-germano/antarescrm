from uuid import uuid4
from datetime import datetime, timezone, date
import pytest
from flask_jwt_extended import create_access_token
from app import create_app
from app.extensions import db
from app.models import Workspace, User, Contact, PipelineStage, Opportunity, Task, LeadForm, FormSubmission, AutomationRule, AutomationRun


@pytest.fixture()
def env():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SQLALCHEMY_ENGINE_OPTIONS': {},
        'JWT_SECRET_KEY': 'test-only-key-with-more-than-thirty-two-characters', 'RATELIMIT_ENABLED': False})
    with app.app_context():
        db.create_all()
        ws = Workspace(name='Client', slug='client', timezone='America/Cuiaba')
        other = Workspace(name='Other', slug='other')
        db.session.add_all([ws, other]); db.session.flush()
        user = User(workspace_id=ws.id, name='Owner', email='owner@example.com', role='owner', password_hash='unused')
        member = User(workspace_id=ws.id, name='Member', email='member@example.com', role='member', password_hash='unused')
        outsider = User(workspace_id=other.id, name='Other', email='other@example.com', role='owner', password_hash='unused')
        stage = PipelineStage(workspace_id=ws.id, name='New', position=0)
        other_stage = PipelineStage(workspace_id=other.id, name='Other stage', position=0)
        db.session.add_all([user, member, outsider, stage, other_stage]); db.session.flush()
        form = LeadForm(workspace_id=ws.id, name='Orçamento', headline='Solicite uma proposta', stage_id=stage.id, source='Campanha', active=True)
        db.session.add(form); db.session.commit()
        def headers(u=user):
            return {'Authorization': 'Bearer ' + create_access_token(identity=u.id, additional_claims={'ver': 0})}
        yield app.test_client(), {'ws': ws, 'other': other, 'owner': user, 'member': member, 'outsider': outsider,
            'stage': stage, 'other_stage': other_stage, 'form': form, 'headers': headers}
        db.session.remove(); db.drop_all()


def submit_body(**kw):
    return dict(submission_key=str(uuid4()), name='Lead de teste', email='lead@example.com', phone='65999999999', consent=True, **kw)


def rule(d, **kw):
    row = AutomationRule(workspace_id=kw.pop('workspace_id', d['ws'].id), name='Primeiro atendimento',
        event=kw.pop('event', 'form.submitted'), task_title='Retornar ao lead', active=kw.pop('active', True),
        due_days=kw.pop('due_days', 0), **kw)
    db.session.add(row); db.session.commit(); return row


def test_capture_creates_contact_opportunity_and_task_atomically(env, monkeypatch):
    client, d = env
    import app.services.automations as module
    monkeypatch.setattr(module, 'now', lambda: datetime(2026, 10, 21, 2, 30, tzinfo=timezone.utc))
    rule(d, assignee_id=d['member'].id)
    response = client.post(f"/api/v1/public/forms/{d['form'].id}/submit", json=submit_body())
    assert response.status_code == 200 and set(response.json) == {'message'}
    contact, opportunity, task = Contact.query.one(), Opportunity.query.one(), Task.query.one()
    assert contact.workspace_id == opportunity.workspace_id == task.workspace_id == d['ws'].id
    assert opportunity.contact_id == task.contact_id == contact.id and task.opportunity_id == opportunity.id
    assert task.assignee_id == d['member'].id and task.due_date == date(2026, 10, 20)
    assert FormSubmission.query.one().consent_text == 'Autorizo o contato em resposta a esta solicitação.'
    assert AutomationRun.query.one().task_id == task.id


def test_submission_retry_is_idempotent(env):
    client, d = env; rule(d)
    body = submit_body()
    for _ in range(2):
        assert client.post(f"/api/v1/public/forms/{d['form'].id}/submit", json=body).status_code == 200
    assert Contact.query.count() == Opportunity.query.count() == FormSubmission.query.count() == Task.query.count() == AutomationRun.query.count() == 1


def test_existing_contact_is_not_overwritten_or_exposed(env):
    client, d = env
    contact = Contact(workspace_id=d['ws'].id, name='Private existing name', email='lead@example.com', source='Existing', phone='123')
    db.session.add(contact); db.session.commit(); rule(d, event='contact.created')
    response = client.post(f"/api/v1/public/forms/{d['form'].id}/submit", json=submit_body())
    assert response.status_code == 200 and set(response.json) == {'message'}
    assert Contact.query.count() == 1 and Contact.query.one().name == 'Private existing name'
    assert Contact.query.one().phone == '123' and Task.query.count() == 0


def test_sources_paused_rules_and_account_isolation(env):
    client, d = env
    rule(d, source='Different'); rule(d, active=False); rule(d, workspace_id=d['other'].id)
    rule(d, source='campanha')
    assert client.post(f"/api/v1/public/forms/{d['form'].id}/submit", json=submit_body()).status_code == 200
    assert Task.query.count() == AutomationRun.query.count() == 1
    h = d['headers'](d['outsider'])
    assert client.get('/api/v1/automations/runs', headers=h).json['total'] == 0
    assert client.get('/api/v1/forms', headers=h).json['total'] == 0
    assert client.get(f"/api/v1/forms/{d['form'].id}/submissions", headers=h).status_code == 404


def test_contact_created_rule_works_for_manual_and_public_leads(env):
    client, d = env; rule(d, event='contact.created')
    assert client.post('/api/v1/contacts', headers=d['headers'](), json={'name': 'Manual lead'}).status_code == 201
    assert Task.query.count() == 1
    assert client.post(f"/api/v1/public/forms/{d['form'].id}/submit", json=submit_body()).status_code == 200
    assert Task.query.count() == AutomationRun.query.count() == 2


@pytest.mark.parametrize('change', ['form', 'workspace'])
def test_inactive_form_or_account_not_public(env, change):
    client, d = env
    (d['form'] if change == 'form' else d['ws']).active = False; db.session.commit()
    path = f"/api/v1/public/forms/{d['form'].id}"
    assert client.get(path).status_code == client.post(path + '/submit', json=submit_body()).status_code == 404
    assert Contact.query.count() == 0


def test_consent_honeypot_unknown_fields_and_validation(env):
    client, d = env
    path = f"/api/v1/public/forms/{d['form'].id}/submit"
    for body in [dict(submit_body(), consent=False), dict(submit_body(), consent=None), dict(submit_body(), website='bot'),
                 dict(submit_body(), name='   '), dict(submit_body(), email='invalid'), dict(submit_body(), workspace_id=d['other'].id), dict(submit_body(), submission_key='invalid')]:
        assert client.post(path, json=body).status_code == 422
    assert Contact.query.count() == FormSubmission.query.count() == 0


def test_form_and_rule_management_requires_admin_and_valid_references(env):
    client, d = env
    body = {'name': 'F', 'headline': 'Hello', 'stage_id': d['other_stage'].id}
    assert client.post('/api/v1/forms', headers=d['headers'](), json=body).status_code == 404
    assert client.post('/api/v1/forms', headers=d['headers'](d['member']), json=body).status_code == 403
    assert client.post('/api/v1/automations', headers=d['headers'](d['member']), json={}).status_code == 403
    assert client.post('/api/v1/automations', headers=d['headers'](), json={'name': 'Rule', 'event': 'contact.created', 'task_title': 'Task', 'assignee_id': d['outsider'].id}).status_code == 404
    assert client.delete('/api/v1/pipeline/stages/' + d['stage'].id, headers=d['headers']()).status_code == 409


def test_inactive_assignee_is_logged_as_skipped(env):
    client, d = env; rule(d, assignee_id=d['member'].id)
    d['member'].active = False; db.session.commit()
    assert client.post(f"/api/v1/public/forms/{d['form'].id}/submit", json=submit_body()).status_code == 200
    assert Task.query.count() == 0 and AutomationRun.query.one().status == 'skipped'


def test_public_response_exposes_only_page_copy(env):
    client, d = env
    response = client.get(f"/api/v1/public/forms/{d['form'].id}")
    assert response.status_code == 200 and set(response.json) == {'headline', 'description', 'consent_text', 'fields', 'brand_name', 'accent_color'}


def test_public_submission_rolls_back_when_action_fails(env, monkeypatch):
    client, d = env
    import app.routes.growth as module
    def failure(*args, **kwargs): raise RuntimeError('simulated internal action failure')
    monkeypatch.setattr(module, 'emit', failure)
    response = client.post(f"/api/v1/public/forms/{d['form'].id}/submit", json=submit_body())
    assert response.status_code == 500
    assert Contact.query.count() == Opportunity.query.count() == FormSubmission.query.count() == 0


def test_form_description_can_be_cleared_without_null_constraint_error(env):
    client, d = env
    d['form'].description = 'Texto anterior'; db.session.commit()
    response = client.patch('/api/v1/forms/' + d['form'].id, headers=d['headers'](), json={'description': None})
    assert response.status_code == 200, response.json
    assert response.json['description'] == ''
    assert client.get('/api/v1/public/forms/' + d['form'].id).json['description'] == ''


def test_public_capture_reuses_mixed_case_email_without_overwriting_contact(env):
    client, d = env
    contact = Contact(workspace_id=d['ws'].id, name='Contato existente', email='Lead@Example.COM', source='Original')
    db.session.add(contact); db.session.commit()
    response = client.post(f"/api/v1/public/forms/{d['form'].id}/submit", json=submit_body())
    assert response.status_code == 200, response.json
    assert Contact.query.count() == 1
    assert Opportunity.query.one().contact_id == contact.id
    assert contact.name == 'Contato existente' and contact.source == 'Original'


def test_public_capture_trims_email_before_validation(env):
    client, d = env
    body = dict(submit_body(), email='  Lead@Example.COM  ')
    response = client.post(f"/api/v1/public/forms/{d['form'].id}/submit", json=body)
    assert response.status_code == 200, response.json
    assert Contact.query.one().email == 'lead@example.com'
