from datetime import datetime, timezone, timedelta
from uuid import uuid4
from test_growth import env
from app.extensions import db
from app.models import Contact, MessageTemplate, AutomationJob, AutomationRun, Task, Activity, InboxMessage
from app.services.automations import process


def setup_flow(client, d, actions, **extra):
    body = {'name': 'Atendimento', 'event': 'contact.created', 'task_title': 'Retornar', 'active': True, 'actions': actions, **extra}
    result = client.post('/api/v1/automations', headers=d['headers'](), json=body)
    assert result.status_code == 201, result.json
    return result.json


def test_tag_condition_sequential_delay_tasks_and_messages(env, monkeypatch):
    client, d = env
    clock = [datetime(2026, 10, 21, 2, 30, tzinfo=timezone.utc)]
    monkeypatch.setattr('app.services.automations.now', lambda: clock[0])
    template = MessageTemplate(workspace_id=d['ws'].id, name='Hello', channel='email', content='Olá {{name}}', subject='Boas-vindas')
    db.session.add(template); db.session.commit()
    setup_flow(client, d, [
        {'kind': 'send_message', 'template_id': template.id},
        {'kind': 'create_task', 'title': 'Telefonar', 'delay_minutes': 60, 'due_days': 1},
        {'kind': 'follow_up', 'title': 'Retorno', 'delay_minutes': 10, 'due_days': 2},
    ], required_tag='Quente', source='Site', assignee_id=d['member'].id)
    for body in [{'name': 'No tag', 'source': 'Site'}, {'name': 'Wrong source', 'source': 'Other', 'tags': ['Quente']}]:
        assert client.post('/api/v1/contacts', headers=d['headers'](), json=body).status_code == 201
    assert AutomationRun.query.count() == 0
    assert client.post('/api/v1/contacts', headers=d['headers'](), json={'name': 'Lead', 'source': 'Site', 'tags': ['Quente'], 'email': 'lead@example.test'}).status_code == 201
    assert AutomationJob.query.count() == 3 and Task.query.count() == 0
    assert len(process(d['ws'].id)) == 1
    assert InboxMessage.query.one().content == 'Olá Lead' and InboxMessage.query.one().status == 'queued'
    assert process(d['ws'].id) == []
    clock[0] += timedelta(minutes=60)
    assert len(process(d['ws'].id)) == 1
    assert Task.query.one().due_date.isoformat() == '2026-10-21'  # Local account day + one.
    assert process(d['ws'].id) == []
    clock[0] += timedelta(minutes=10)
    assert len(process(d['ws'].id)) == 1 and Activity.query.one().kind == 'follow_up'
    assert AutomationRun.query.one().status == 'completed'
    assert process(d['ws'].id) == [] and InboxMessage.query.count() == Task.query.count() == Activity.query.count() == 1
    assert client.get('/api/v1/automations/jobs', headers=d['headers'](d['outsider'])).json['total'] == 0


def test_paused_rule_skips_pending_actions(env):
    client, d = env
    rule = setup_flow(client, d, [{'kind': 'create_task', 'title': 'Task'}])
    client.post('/api/v1/contacts', headers=d['headers'](), json={'name': 'Lead'})
    assert client.patch('/api/v1/automations/' + rule['id'], headers=d['headers'](), json={'active': False}).status_code == 200
    assert len(process(d['ws'].id)) == 1 and Task.query.count() == 0
    assert AutomationJob.query.one().status == 'skipped'


def test_failed_action_rolls_back_and_stops_following_steps(env):
    client, d = env
    template = MessageTemplate(workspace_id=d['ws'].id, name='Hello', channel='email', content='Hello')
    db.session.add(template); db.session.commit()
    setup_flow(client, d, [{'kind': 'send_message', 'template_id': template.id}, {'kind': 'create_task', 'title': 'Next step'}])
    client.post('/api/v1/contacts', headers=d['headers'](), json={'name': 'No email'})
    assert len(process(d['ws'].id)) == 2
    assert [row.status for row in AutomationJob.query.order_by(AutomationJob.position)] == ['failed', 'skipped']
    assert InboxMessage.query.count() == Task.query.count() == 0 and AutomationRun.query.one().status == 'failed'


def test_cross_account_template_and_partial_actions_rejected(env):
    client, d = env
    template = MessageTemplate(workspace_id=d['other'].id, name='Private', channel='email', content='Private')
    db.session.add(template); db.session.commit()
    body = {'name': 'Bad', 'event': 'contact.created', 'task_title': 'Task', 'actions': [{'kind': 'send_message', 'template_id': template.id}]}
    assert client.post('/api/v1/automations', headers=d['headers'](), json=body).status_code == 404
    rule = setup_flow(client, d, [{'kind': 'create_task', 'title': 'Task'}])
    for action in [{'title': 'Missing kind'}, {'kind': 'send_message'}, {'kind': 'create_task'}, {'kind': 'create_task', 'title': 'Task', 'delay_minutes': -1}]:
        assert client.patch('/api/v1/automations/' + rule['id'], headers=d['headers'](), json={'actions': [action]}).status_code == 422


def test_worker_command_executes_without_external_providers(env):
    client, d = env
    setup_flow(client, d, [{'kind': 'create_task', 'title': 'Worker task'}])
    client.post('/api/v1/contacts', headers=d['headers'](), json={'name': 'Lead'})
    result = client.application.test_cli_runner().invoke(args=['run-worker', '--once'])
    assert result.exit_code == 0, result.output
    assert Task.query.one().title == 'Worker task'
