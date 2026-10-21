from datetime import datetime, timedelta, timezone
from test_growth import env
from app.extensions import db
from app.models import Contact, Opportunity, StageHistory, Task, Activity, now


def seed(d):
    ws, stage = d['ws'], d['stage']
    stage.probability = 50
    c1 = Contact(workspace_id=ws.id, name='A', source='Instagram')
    c2 = Contact(workspace_id=ws.id, name='B', source='Indicação')
    db.session.add_all([c1, c2])
    db.session.flush()
    recent = now() - timedelta(days=5)
    won = Opportunity(
        workspace_id=ws.id,
        contact_id=c1.id,
        stage_id=stage.id,
        owner_id=d['owner'].id,
        title='Ganho',
        amount=1000,
        status='won',
        closed_at=recent,
        created_at=recent - timedelta(days=10),
    )
    lost = Opportunity(
        workspace_id=ws.id,
        contact_id=c2.id,
        stage_id=stage.id,
        owner_id=d['owner'].id,
        title='Perdido',
        amount=400,
        status='lost',
        closed_at=recent,
        loss_reason='Preço',
    )
    open_ = Opportunity(
        workspace_id=ws.id,
        contact_id=c2.id,
        stage_id=stage.id,
        owner_id=d['owner'].id,
        title='Aberto',
        amount=2000,
        status='open',
        created_at=now() - timedelta(days=40),
    )
    db.session.add_all([won, lost, open_])
    db.session.flush()
    db.session.add(
        StageHistory(
            workspace_id=ws.id,
            opportunity_id=open_.id,
            to_stage_id=stage.id,
            user_id=d['owner'].id,
            created_at=now() - timedelta(days=40),
        )
    )
    db.session.add(Task(workspace_id=ws.id, title='t', status='done', completed_at=recent, assignee_id=d['owner'].id))
    db.session.add(
        Activity(
            workspace_id=ws.id, title='a', kind='call', status='completed', scheduled_at=recent, owner_id=d['owner'].id
        )
    )
    db.session.commit()


def test_overview_kpis_funnel_team_sources_and_forecast(env):
    client, d = env
    seed(d)
    data = client.get('/api/v1/reports/overview', headers=d['headers']()).get_json()
    cur = data['current']
    assert (
        cur['won_amount'] == 1000
        and cur['won_count'] == 1
        and cur['lost_count'] == 1
        and cur['conversion_rate'] == 50.0
    )
    assert cur['sales_cycle_days'] is not None and 9 <= cur['sales_cycle_days'] <= 11
    assert (
        data['pipeline']['open_amount'] == 2000
        and data['pipeline']['weighted_amount'] == 1000.0
        and data['pipeline']['stale_count'] == 1
    )
    assert data['loss_reasons'][0]['reason'] == 'Preço'
    assert (
        data['team'][0]['won_amount'] == 1000
        and data['team'][0]['tasks_done'] == 1
        and data['team'][0]['activities_done'] == 1
    )
    assert any(row['source'] == 'Instagram' and row['won_amount'] == 1000 for row in data['sources'])
    assert data['period']['days'] == 30 and len(data['timeline']) == 30
    assert data['top_stale'][0]['title'] == 'Aberto'


def test_overview_validates_period_and_isolates_accounts(env):
    client, d = env
    seed(d)
    assert (
        client.get('/api/v1/reports/overview?start=2026-02-01&end=2026-01-01', headers=d['headers']()).status_code
        == 400
    )
    other = client.get('/api/v1/reports/overview', headers=d['headers'](d['outsider'])).get_json()
    assert other['current']['won_count'] == 0 and other['pipeline']['open_count'] == 0
