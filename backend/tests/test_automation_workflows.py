from datetime import datetime, timedelta, timezone
from uuid import uuid4
from test_growth import env, rule
from app.extensions import db
from app.models import AutomationRun, AutomationJob, Contact, Task, Activity, InboxMessage, MessageTemplate
from app.services.automations import process


def contact_for(d, **kw):
    row = Contact(workspace_id=d['ws'].id, name=kw.pop('name', 'Lead'), tags=kw.pop('tags', []), **kw)
    db.session.add(row)
    db.session.commit()
    return row


def template_for(d, **kw):
    row = MessageTemplate(
        workspace_id=d['ws'].id,
        name='Boas-vindas',
        channel=kw.pop('channel', 'email'),
        subject=kw.pop('subject', 'Olá {{name}}'),
        content=kw.pop('content', 'Oi {{name}}'),
    )
    db.session.add(row)
    db.session.commit()
    return row


def test_actions_schedule_jobs_with_cumulative_delay_and_run_stays_queued(env, monkeypatch):
    client, d = env
    import app.services.automations as module

    base = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(module, 'now', lambda: base)
    template = template_for(d)
    rule(
        d,
        event='contact.created',
        actions=[
            {'kind': 'create_task', 'title': 'Ligar', 'delay_minutes': 0, 'due_days': 1},
            {'kind': 'send_message', 'template_id': template.id, 'delay_minutes': 30},
            {'kind': 'follow_up', 'title': 'Revisar', 'delay_minutes': 90, 'due_days': 2},
        ],
    )
    contact = contact_for(d)
    module.emit(d['ws'].id, 'contact.created', contact.id, contact)
    db.session.commit()
    assert AutomationRun.query.one().status == 'queued'
    jobs = AutomationJob.query.order_by(AutomationJob.position).all()
    assert [j.scheduled_at for j in jobs] == [base, base + timedelta(minutes=30), base + timedelta(minutes=120)]
    assert Task.query.count() == 0  # Nothing executes until the worker runs the due steps.


def test_process_runs_steps_in_order_and_skips_step_due_before_predecessor(env, monkeypatch):
    client, d = env
    import app.services.automations as module

    base = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(module, 'now', lambda: base)
    contact = contact_for(d)
    rule(
        d,
        event='contact.created',
        actions=[
            {'kind': 'create_task', 'title': 'Primeiro', 'delay_minutes': 0, 'due_days': 0},
            {'kind': 'create_task', 'title': 'Segundo', 'delay_minutes': 0, 'due_days': 0},
        ],
    )
    module.emit(d['ws'].id, 'contact.created', contact.id, contact)
    db.session.commit()
    first, second = AutomationJob.query.order_by(AutomationJob.position).all()
    second.scheduled_at = base - timedelta(minutes=1)  # Simulate clock skew making step 2 look due first.
    db.session.commit()
    process(d['ws'].id, limit=10)
    first, second = AutomationJob.query.order_by(AutomationJob.position).all()
    assert first.status == 'completed' and second.status == 'skipped'
    assert Task.query.count() == 1 and Task.query.one().title == 'Primeiro'
    assert AutomationRun.query.one().status == 'skipped'


def test_send_message_action_enqueues_rendered_inbox_message(env, monkeypatch):
    client, d = env
    import app.services.automations as module

    monkeypatch.setattr(module, 'now', lambda: datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc))
    template = template_for(d, subject='Olá {{name}}', content='Oi {{name}}, bem-vindo')
    contact = contact_for(d, name='Ana', email='ana@example.test')
    rule(d, event='contact.created', actions=[{'kind': 'send_message', 'template_id': template.id, 'delay_minutes': 0}])
    module.emit(d['ws'].id, 'contact.created', contact.id, contact)
    db.session.commit()
    processed = process(d['ws'].id)
    assert len(processed) == 1 and processed[0]['status'] == 'completed'
    message = InboxMessage.query.one()
    assert message.content == 'Oi Ana, bem-vindo' and message.subject == 'Olá Ana'
    assert AutomationJob.query.one().result_id == message.id


def test_follow_up_action_creates_activity_with_cumulative_offset(env, monkeypatch):
    client, d = env
    import app.services.automations as module

    base = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(module, 'now', lambda: base)
    contact = contact_for(d)
    rule(
        d,
        event='contact.created',
        assignee_id=d['owner'].id,
        actions=[
            {'kind': 'follow_up', 'title': 'Checar interesse', 'delay_minutes': 15, 'due_days': 3},
        ],
    )
    module.emit(d['ws'].id, 'contact.created', contact.id, contact)
    db.session.commit()
    monkeypatch.setattr(module, 'now', lambda: base + timedelta(minutes=15))
    process(d['ws'].id)
    activity = Activity.query.one()
    assert activity.kind == 'follow_up' and activity.owner_id == d['owner'].id and activity.contact_id == contact.id
    assert activity.scheduled_at == base + timedelta(minutes=15) + timedelta(days=3)


def test_required_tag_condition_filters_contacts(env, monkeypatch):
    client, d = env
    import app.services.automations as module

    monkeypatch.setattr(module, 'now', lambda: datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc))
    rule(
        d,
        event='contact.created',
        required_tag='vip',
        actions=[{'kind': 'create_task', 'title': 'Atender VIP', 'delay_minutes': 0, 'due_days': 0}],
    )
    plain = contact_for(d, name='Comum', tags=[])
    vip = contact_for(d, name='VIP', tags=['vip'])
    module.emit(d['ws'].id, 'contact.created', plain.id, plain)
    module.emit(d['ws'].id, 'contact.created', vip.id, vip)
    db.session.commit()
    assert AutomationRun.query.count() == 1 and AutomationRun.query.one().contact_id == vip.id


def test_send_message_with_unavailable_template_fails_job_without_crashing_worker(env, monkeypatch):
    client, d = env
    import app.services.automations as module

    monkeypatch.setattr(module, 'now', lambda: datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc))
    contact = contact_for(d)
    rule(
        d, event='contact.created', actions=[{'kind': 'send_message', 'template_id': str(uuid4()), 'delay_minutes': 0}]
    )
    module.emit(d['ws'].id, 'contact.created', contact.id, contact)
    db.session.commit()
    process(d['ws'].id)
    assert AutomationJob.query.one().status == 'failed'
    assert AutomationRun.query.one().status == 'failed'
    assert InboxMessage.query.count() == 0


def test_job_skipped_when_contact_is_archived_before_its_turn(env, monkeypatch):
    client, d = env
    import app.services.automations as module

    monkeypatch.setattr(module, 'now', lambda: datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc))
    contact = contact_for(d)
    rule(
        d,
        event='contact.created',
        assignee_id=d['member'].id,
        actions=[{'kind': 'create_task', 'title': 'X', 'delay_minutes': 0, 'due_days': 0}],
    )
    module.emit(d['ws'].id, 'contact.created', contact.id, contact)
    db.session.commit()
    contact.archived = True
    db.session.commit()
    process(d['ws'].id)
    assert AutomationJob.query.one().status == 'skipped' and Task.query.count() == 0


def test_jobs_and_process_routes_are_scoped_and_role_restricted(env, monkeypatch):
    client, d = env
    import app.services.automations as module

    monkeypatch.setattr(module, 'now', lambda: datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc))
    contact = contact_for(d)
    rule(d, event='contact.created', actions=[{'kind': 'create_task', 'title': 'X', 'delay_minutes': 0, 'due_days': 0}])
    module.emit(d['ws'].id, 'contact.created', contact.id, contact)
    db.session.commit()
    assert client.get('/api/v1/automations/jobs', headers=d['headers'](d['outsider'])).json['total'] == 0
    assert client.get('/api/v1/automations/jobs', headers=d['headers']()).json['total'] == 1
    assert client.post('/api/v1/automations/process', headers=d['headers'](d['member']), json={}).status_code == 403
    response = client.post('/api/v1/automations/process', headers=d['headers'](), json={})
    assert response.status_code == 200 and len(response.json['items']) == 1
    assert Task.query.count() == 1


def test_rule_action_validation_requires_template_or_title_and_scopes_template(env):
    client, d = env
    base_body = {'name': 'Fluxo', 'event': 'contact.created', 'task_title': 'Fallback', 'due_days': 0}
    assert (
        client.post(
            '/api/v1/automations', headers=d['headers'](), json={**base_body, 'actions': [{'kind': 'send_message'}]}
        ).status_code
        == 422
    )
    assert (
        client.post(
            '/api/v1/automations', headers=d['headers'](), json={**base_body, 'actions': [{'kind': 'create_task'}]}
        ).status_code
        == 422
    )
    foreign = {**base_body, 'actions': [{'kind': 'send_message', 'template_id': str(uuid4())}]}
    assert client.post('/api/v1/automations', headers=d['headers'](), json=foreign).status_code == 404
    template = template_for(d)
    ok = {**base_body, 'actions': [{'kind': 'send_message', 'template_id': template.id}]}
    response = client.post('/api/v1/automations', headers=d['headers'](), json=ok)
    assert response.status_code == 201 and response.json['actions'][0]['template_id'] == template.id
