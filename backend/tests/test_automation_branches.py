from datetime import datetime, timedelta, timezone

from test_automation_workflows import contact_for
from test_growth import env, rule  # noqa: F401
from app.extensions import db
from app.models import AutomationJob, AutomationRule, AutomationRun, Contact, Task
from app.services.automations import process

VIP = {'mode': 'all', 'items': [{'field': 'tag', 'operator': 'equals', 'value': 'vip'}]}
BASE = {'name': 'Fluxo', 'event': 'contact.created', 'task_title': 'Fallback', 'due_days': 0}


def branch(yes=None, no=None, **kw):
    return {'kind': 'branch', 'conditions': VIP, 'yes': yes or [], 'no': no or [], 'delay_minutes': 0, **kw}


def task(title, **kw):
    return {'kind': 'create_task', 'title': title, 'delay_minutes': 0, 'due_days': 0, **kw}


def run_flow(d, monkeypatch, tags, actions):
    import app.services.automations as module

    base = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(module, 'now', lambda: base)
    rule(d, event='contact.created', actions=actions)
    contact = contact_for(d, tags=tags)
    module.emit(d['ws'].id, 'contact.created', contact.id, contact)
    db.session.commit()
    process(d['ws'].id, limit=20)
    return contact


def test_branch_follows_yes_path_when_conditions_match(env, monkeypatch):
    client, d = env
    run_flow(d, monkeypatch, ['vip'], [task('Antes'), branch(yes=[task('VIP')], no=[task('Comum')])])
    assert sorted(t.title for t in Task.query.all()) == ['Antes', 'VIP']
    jobs = AutomationJob.query.order_by(AutomationJob.position).all()
    assert [j.action['kind'] for j in jobs] == ['create_task', 'branch', 'create_task']
    assert 'Sim' in jobs[1].detail and jobs[2].position == 2
    assert AutomationRun.query.one().status == 'completed'


def test_branch_follows_no_path_and_nested_branches(env, monkeypatch):
    client, d = env
    inner = branch(yes=[task('Nunca')], no=[task('Interno não')])
    run_flow(d, monkeypatch, [], [branch(yes=[task('VIP')], no=[task('Comum'), inner])])
    assert sorted(t.title for t in Task.query.all()) == ['Comum', 'Interno não']
    assert [j.position for j in AutomationJob.query.order_by(AutomationJob.position)] == [0, 1, 2, 3]


def test_branch_is_evaluated_when_reached_and_path_waits_its_delay(env, monkeypatch):
    client, d = env
    import app.services.automations as module

    base = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)
    clock = {'now': base}
    monkeypatch.setattr(module, 'now', lambda: clock['now'])
    rule(d, event='contact.created', actions=[branch(yes=[task('VIP', delay_minutes=60)], delay_minutes=30)])
    contact = contact_for(d)
    module.emit(d['ws'].id, 'contact.created', contact.id, contact)
    db.session.commit()
    contact.tags = ['vip']  # Tagged after the trigger but before the branch is reached.
    db.session.commit()
    clock['now'] = base + timedelta(minutes=30)
    process(d['ws'].id, limit=10)
    pending = AutomationJob.query.filter_by(status='pending').one()
    assert pending.scheduled_at == base + timedelta(minutes=90) and Task.query.count() == 0
    assert AutomationRun.query.one().status == 'queued'
    clock['now'] = base + timedelta(minutes=90)
    process(d['ws'].id, limit=10)
    assert Task.query.one().title == 'VIP'
    assert AutomationRun.query.one().status == 'completed'


def test_reply_cancels_steps_queued_by_a_branch(env, monkeypatch):
    client, d = env
    import app.services.automations as module

    contact = run_flow(d, monkeypatch, ['vip'], [branch(yes=[task('Depois', delay_minutes=60)])])
    AutomationRule.query.one().stop_on_reply = True
    run = AutomationRun.query.one()
    run.config_snapshot = {**run.config_snapshot, 'stop_on_reply': True}
    db.session.commit()
    module.received_reply(d['ws'].id, db.session.get(Contact, contact.id), 'reply-1')
    db.session.commit()
    assert AutomationJob.query.filter_by(status='cancelled').count() == 1


def test_branch_validation(env):
    client, d = env
    post = lambda actions: client.post(  # noqa: E731
        '/api/v1/automations', headers=d['headers'](), json={**BASE, 'actions': actions}
    )
    assert post([branch(yes=[task('A')]), task('Depois')]).status_code == 422  # Must be the last step.
    assert post([branch(conditions={'mode': 'all', 'items': []})]).status_code == 422
    assert post([branch(yes=[{'kind': 'send_message'}])]).status_code == 422  # Nested steps are validated.
    too_deep = task('Fim')
    for _ in range(6):
        too_deep = branch(yes=[too_deep])
    assert post([too_deep]).status_code == 422
    ten = [task(str(i)) for i in range(10)]
    assert post([*ten[:9], branch(yes=ten, no=ten)]).status_code == 201  # Exactly 30 steps.
    nested_no = [*ten[:9], branch(yes=[task('Extra')])]
    assert post([*ten[:9], branch(yes=ten, no=nested_no)]).status_code == 422  # 31 across all paths.
    saved = post([branch(yes=[task('A')], no=[task('B')])])
    assert saved.status_code == 201
    stored = db.session.get(AutomationRule, saved.json['id']).actions[0]
    assert stored['yes'][0]['title'] == 'A' and stored['no'][0]['title'] == 'B'
    assert 'yes' not in stored['yes'][0]


def test_card_offsets_are_stored_with_each_step(env):
    client, d = env
    actions = [branch(yes=[task('A', offset={'x': 40, 'y': -12})], offset={'x': 0, 'y': 80})]
    saved = client.post('/api/v1/automations', headers=d['headers'](), json={**BASE, 'actions': actions})
    assert saved.status_code == 201
    stored = db.session.get(AutomationRule, saved.json['id']).actions[0]
    assert stored['offset'] == {'x': 0, 'y': 80} and stored['yes'][0]['offset'] == {'x': 40, 'y': -12}
    bad = [task('A', offset={'x': 'longe', 'y': 0})]
    assert client.post('/api/v1/automations', headers=d['headers'](), json={**BASE, 'actions': bad}).status_code == 422
