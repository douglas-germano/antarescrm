from datetime import datetime, timezone
from test_growth import env, rule
from test_automation_workflows import contact_for
from app.extensions import db
from app.models import AutomationRun, AutomationJob, Opportunity, PipelineStage, StageHistory
import app.services.automations as module
from app.services.automations import process


def deal_for(d, contact, stage=None):
    row = Opportunity(workspace_id=d['ws'].id, contact_id=contact.id, stage_id=(stage or d['stage']).id, title='Negócio', amount=100)
    db.session.add(row); db.session.commit(); return row


def test_add_tag_and_move_stage_actions_run(env):
    client, d = env
    target = PipelineStage(workspace_id=d['ws'].id, name='Proposta', position=1)
    db.session.add(target); db.session.commit()
    rule(d, event='opportunity.created', actions=[
        {'kind': 'add_tag', 'tag': 'quente', 'delay_minutes': 0},
        {'kind': 'move_stage', 'stage_id': target.id, 'delay_minutes': 0},
    ])
    contact = contact_for(d)
    deal = deal_for(d, contact)
    module.emit(d['ws'].id, 'opportunity.created', deal.id, contact, deal.id)
    db.session.commit()
    process(d['ws'].id)
    db.session.refresh(contact); db.session.refresh(deal)
    assert 'quente' in contact.tags
    assert deal.stage_id == target.id
    assert StageHistory.query.filter_by(opportunity_id=deal.id, to_stage_id=target.id).count() == 1
    assert AutomationRun.query.one().status == 'completed'


def test_new_actions_are_validated_and_stage_must_belong_to_account(env):
    client, d = env
    base = {'name': 'Teste', 'event': 'opportunity.created', 'task_title': 'x'}
    bad_tag = client.post('/api/v1/automations', json={**base, 'actions': [{'kind': 'add_tag'}]}, headers=d['headers']())
    assert bad_tag.status_code == 422
    foreign = client.post('/api/v1/automations', json={**base, 'actions': [{'kind': 'move_stage', 'stage_id': d['other_stage'].id}]}, headers=d['headers']())
    assert foreign.status_code == 404
    ok = client.post('/api/v1/automations', json={**base, 'actions': [{'kind': 'move_stage', 'stage_id': d['stage'].id}]}, headers=d['headers']())
    assert ok.status_code == 201


def test_rule_stats_cancel_retry_and_delete_rules(env):
    client, d = env
    row = rule(d, event='contact.created', actions=[{'kind': 'create_task', 'title': 'Ligar', 'delay_minutes': 60, 'due_days': 0}])
    contact = contact_for(d)
    module.emit(d['ws'].id, 'contact.created', contact.id, contact)
    db.session.commit()
    listed = client.get('/api/v1/automations', headers=d['headers']()).get_json()['items'][0]
    assert listed['stats']['runs'] == 1 and listed['stats']['last_run_at']
    run = client.get('/api/v1/automations/runs', headers=d['headers']()).get_json()['items'][0]
    assert run['contact_name'] == 'Lead'
    # Cannot delete a rule that already has history.
    assert client.delete(f'/api/v1/automations/{row.id}', headers=d['headers']()).status_code == 409
    # Member cannot cancel.
    assert client.post(f"/api/v1/automations/runs/{run['id']}/cancel", headers=d['headers'](d['member'])).status_code == 403
    assert client.post(f"/api/v1/automations/runs/{run['id']}/cancel", headers=d['headers']()).status_code == 200
    assert AutomationJob.query.one().status == 'cancelled'
    assert client.post(f"/api/v1/automations/runs/{run['id']}/cancel", headers=d['headers']()).status_code == 409
    job = AutomationJob.query.one()
    assert client.post(f'/api/v1/automations/jobs/{job.id}/retry', headers=d['headers']()).status_code == 409  # only failed/skipped
    job.status = 'failed'; db.session.commit()
    assert client.post(f'/api/v1/automations/jobs/{job.id}/retry', headers=d['headers']()).status_code == 200
    assert AutomationJob.query.one().status == 'pending'
    fresh = rule(d, event='contact.created', actions=[])
    assert client.delete(f'/api/v1/automations/{fresh.id}', headers=d['headers']()).status_code == 204
