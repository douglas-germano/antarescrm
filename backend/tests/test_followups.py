from datetime import date, datetime, timedelta, timezone
import pytest
from flask_jwt_extended import create_access_token
from app import create_app
from app.extensions import db
from app.models import Workspace, User, Contact, PipelineStage, Opportunity, Activity, Task


@pytest.fixture()
def setup_app(monkeypatch):
    import app.services.followups as module
    fixed = datetime(2026, 10, 19, 2, 0, tzinfo=timezone.utc)  # Oct 18, 22:00 in Cuiaba
    monkeypatch.setattr(module, 'now', lambda: fixed)
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SQLALCHEMY_ENGINE_OPTIONS': {},
                      'JWT_SECRET_KEY': 'test-only-key-with-more-than-thirty-two-characters', 'RATELIMIT_ENABLED': False})
    with app.app_context():
        db.create_all()
        workspace = Workspace(name='Workspace A', slug='test-a', timezone='America/Cuiaba')
        other = Workspace(name='Workspace B', slug='test-b', timezone='UTC')
        db.session.add_all([workspace, other]); db.session.flush()
        user = User(workspace_id=workspace.id, name='A', email='a@example.invalid', password_hash='unused', role='owner')
        colleague = User(workspace_id=workspace.id, name='B', email='b@example.invalid', password_hash='unused')
        other_user = User(workspace_id=other.id, name='Other', email='other@example.invalid', password_hash='unused')
        stage = PipelineStage(workspace_id=workspace.id, name='Novo', position=0)
        other_stage = PipelineStage(workspace_id=other.id, name='Novo', position=0)
        db.session.add_all([user, colleague, other_user, stage, other_stage]); db.session.flush()
        token = create_access_token(identity=user.id, additional_claims={'ver': 0})
        def deal(title, **kw):
            row = Opportunity(workspace_id=kw.pop('workspace_id', workspace.id), stage_id=kw.pop('stage_id', stage.id),
                              owner_id=kw.pop('owner_id', user.id), title=title, amount=100, **kw)
            db.session.add(row); db.session.flush(); return row
        data = {'workspace': workspace, 'other': other, 'user': user, 'colleague': colleague, 'other_user': other_user,
                'stage': stage, 'other_stage': other_stage, 'deal': deal, 'fixed': fixed}
        yield app.test_client(), {'Authorization': 'Bearer ' + token}, data
        db.session.remove(); db.drop_all()


def test_authentication_required(setup_app):
    client, _, _ = setup_app
    assert client.get('/api/v1/reports/follow-ups').status_code == 401


def test_missing_action_and_closed_deal_excluded(setup_app):
    client, headers, data = setup_app
    data['deal']('Sem ação'); data['deal']('Encerrado', status='won'); db.session.commit()
    response = client.get('/api/v1/reports/follow-ups', headers=headers).get_json()
    assert response['total'] == 1
    assert response['items'][0]['reason'] == 'no_next_action'
    assert response['summary']['no_next_action'] == 1


def test_pending_actions_and_local_date_boundary(setup_app):
    client, headers, data = setup_app
    today_task = data['deal']('Tarefa ainda no prazo')
    future = data['deal']('Atividade futura')
    late = data['deal']('Atividade vencida')
    cancelled = data['deal']('Cancelada não conta')
    db.session.add_all([
        Task(workspace_id=data['workspace'].id, opportunity_id=today_task.id, title='Hoje local', due_date=date(2026, 10, 18), status='todo'),
        Activity(workspace_id=data['workspace'].id, opportunity_id=future.id, title='Amanhã', scheduled_at=data['fixed'] + timedelta(days=1)),
        Activity(workspace_id=data['workspace'].id, opportunity_id=late.id, title='Ontem', scheduled_at=data['fixed'] - timedelta(days=1)),
        Activity(workspace_id=data['workspace'].id, opportunity_id=cancelled.id, title='Não considerar', scheduled_at=data['fixed'] + timedelta(days=1), status='cancelled'),
    ]); db.session.commit()
    rows = client.get('/api/v1/reports/follow-ups', headers=headers).get_json()['items']
    assert {row['title']: row['reason'] for row in rows} == {'Atividade vencida': 'overdue_action', 'Cancelada não conta': 'no_next_action'}


def test_workspace_isolation_and_mine_filter(setup_app):
    client, headers, data = setup_app
    own = data['deal']('Meu negócio')
    data['deal']('Do colega', owner_id=data['colleague'].id)
    data['deal']('Segredo externo', workspace_id=data['other'].id, stage_id=data['other_stage'].id, owner_id=data['other_user'].id)
    # Malformed external association must not affect the current workspace report.
    db.session.add(Activity(workspace_id=data['other'].id, opportunity_id=own.id, title='Ação externa', scheduled_at=data['fixed'] + timedelta(days=1)))
    db.session.commit()
    assert client.get('/api/v1/reports/follow-ups', headers=headers).get_json()['total'] == 2
    rows = client.get('/api/v1/reports/follow-ups?mine=true', headers=headers).get_json()['items']
    assert len(rows) == 1 and rows[0]['id'] == own.id and rows[0]['reason'] == 'no_next_action'


def test_overdue_close_and_completed_task(setup_app):
    client, headers, data = setup_app
    late_close = data['deal']('Previsão vencida', expected_close_date=date(2026, 10, 17))
    done_task = data['deal']('Apenas tarefa concluída')
    db.session.add(Activity(workspace_id=data['workspace'].id, opportunity_id=late_close.id, title='Próximo passo', scheduled_at=data['fixed'] + timedelta(days=1)))
    db.session.add(Task(workspace_id=data['workspace'].id, opportunity_id=done_task.id, title='Finalizada', due_date=date(2026, 10, 17), status='done'))
    db.session.commit()
    rows = client.get('/api/v1/reports/follow-ups', headers=headers).get_json()['items']
    assert {row['title']: row['reason'] for row in rows} == {'Previsão vencida': 'overdue_close', 'Apenas tarefa concluída': 'no_next_action'}


def test_undated_tasks_do_not_claim_scheduled_next_step(setup_app):
    client, headers, data = setup_app
    row = data['deal']('Sem data')
    db.session.add(Task(workspace_id=data['workspace'].id, opportunity_id=row.id, title='Sem prazo', status='doing'))
    db.session.commit()
    result = client.get('/api/v1/reports/follow-ups', headers=headers).get_json()
    assert result['items'][0]['reason'] == 'no_next_action'


def test_schedule_complete_and_note_workflow(setup_app):
    client, headers, data = setup_app
    contact = Contact(workspace_id=data['workspace'].id, name='Lead de teste')
    db.session.add(contact); db.session.flush()
    deal = data['deal']('Fluxo comercial', contact_id=contact.id)
    db.session.commit()
    assert client.get('/api/v1/reports/follow-ups', headers=headers).get_json()['total'] == 1
    response = client.post('/api/v1/activities', headers=headers, json={
        'title': 'Contexto da conversa', 'notes': 'Orçamento alinhado.', 'kind': 'note', 'status': 'completed',
        'scheduled_at': data['fixed'].isoformat(), 'opportunity_id': deal.id, 'contact_id': contact.id,
    })
    assert response.status_code == 201
    assert client.get('/api/v1/reports/follow-ups', headers=headers).get_json()['total'] == 1
    response = client.post('/api/v1/activities', headers=headers, json={
        'title': 'Retornar para o lead', 'kind': 'follow_up', 'status': 'pending',
        'scheduled_at': (data['fixed'] + timedelta(days=1)).isoformat(), 'opportunity_id': deal.id, 'contact_id': contact.id,
    })
    assert response.status_code == 201
    activity_id = response.get_json()['id']
    assert client.get('/api/v1/reports/follow-ups', headers=headers).get_json()['total'] == 0
    timeline = client.get('/api/v1/contacts/' + contact.id + '/timeline', headers=headers).get_json()
    assert len(timeline['activities']) == 2 and len(timeline['opportunities']) == 1
    assert client.patch('/api/v1/activities/' + activity_id, headers=headers, json={'status': 'completed'}).status_code == 200
    assert client.get('/api/v1/reports/follow-ups', headers=headers).get_json()['items'][0]['reason'] == 'no_next_action'


def test_activity_cannot_link_another_workspace(setup_app):
    client, headers, data = setup_app
    foreign = Contact(workspace_id=data['other'].id, name='Contato privado')
    db.session.add(foreign); db.session.commit()
    response = client.post('/api/v1/activities', headers=headers, json={
        'title': 'Não permitir', 'kind': 'follow_up', 'scheduled_at': data['fixed'].isoformat(), 'contact_id': foreign.id,
    })
    assert response.status_code == 404
    assert Activity.query.count() == 0


def test_order_and_missing_deadlines(setup_app):
    client, headers, data = setup_app
    missing = data['deal']('Sem próximo passo')
    close = data['deal']('Previsão antiga', expected_close_date=date(2026, 10, 17))
    task_deal = data['deal']('Tarefa atrasada')
    db.session.add(Task(workspace_id=data['workspace'].id, opportunity_id=task_deal.id, title='Retorno pendente', due_date=date(2026, 10, 17), status='doing'))
    db.session.commit()
    report = client.get('/api/v1/reports/follow-ups', headers=headers).get_json()
    assert [row['id'] for row in report['items']] == [task_deal.id, close.id, missing.id]
    assert report['summary'] == {'overdue_action': 1, 'overdue_close': 1, 'no_next_action': 1}
