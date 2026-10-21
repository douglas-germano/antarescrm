from datetime import datetime, timezone, timedelta
from uuid import uuid4
import pytest
from test_growth import env, submit_body, rule
from app.extensions import db
from app.models import (
    Contact,
    FormSubmission,
    Opportunity,
    BookingCalendar,
    Booking,
    Activity,
    WorkerHeartbeat,
    AutomationRun,
    AutomationJob,
    InboxMessage,
)
from app.services import booking
from app.services.automations import process, received_reply
from app.services.communications import enqueue, dispatch


def test_dynamic_fields_are_validated_mapped_and_snapshotted(env):
    client, d = env
    fields = [
        {
            'key': 'interesse',
            'label': 'Interesse',
            'type': 'select',
            'required': True,
            'options': ['Serviço', 'Produto'],
            'map_to': 'interesse',
        },
        {
            'key': 'detalhes',
            'label': 'Detalhes',
            'type': 'text',
            'required': True,
            'show_if': {'field': 'interesse', 'equals': 'Serviço'},
        },
    ]
    assert (
        client.patch('/api/v1/forms/' + d['form'].id, headers=d['headers'](), json={'fields': fields}).status_code
        == 200
    )
    public = client.get('/api/v1/public/forms/' + d['form'].id).json
    assert 'map_to' not in public['fields'][0]
    path = '/api/v1/public/forms/' + d['form'].id + '/submit'
    assert client.post(path, json=submit_body()).status_code == 422
    body = dict(submit_body(), answers={'interesse': 'Serviço'})
    assert client.post(path, json=body).status_code == 422
    body['answers']['detalhes'] = 'Visita técnica'
    body['attribution'] = {'utm_source': 'instagram', 'utm_campaign': 'outubro'}
    assert client.post(path, json=body).status_code == 200
    assert Contact.query.one().custom_fields == {'interesse': 'Serviço'}
    snapshot = FormSubmission.query.one()
    assert snapshot.answers['detalhes'] == 'Visita técnica' and snapshot.attribution['utm_source'] == 'instagram'
    assert client.post(path, json=body).status_code == 200 and FormSubmission.query.count() == 1
    assert client.patch('/api/v1/forms/' + d['form'].id, headers=d['headers'](), json={'fields': []}).status_code == 200
    assert snapshot.answers['detalhes'] == 'Visita técnica'


def test_hidden_required_field_is_not_required_or_mapped(env):
    client, d = env
    d['form'].fields = [
        {'key': 'accept', 'label': 'Sim', 'type': 'checkbox', 'required': False, 'options': []},
        {
            'key': 'secret',
            'label': 'Outro',
            'type': 'text',
            'required': True,
            'show_if': {'field': 'accept', 'equals': True},
            'map_to': 'secret',
        },
    ]
    db.session.commit()
    body = dict(submit_body(), answers={'accept': False, 'secret': 'forged hidden answer'})
    assert client.post('/api/v1/public/forms/' + d['form'].id + '/submit', json=body).status_code == 200
    assert 'secret' not in FormSubmission.query.one().answers and Contact.query.one().custom_fields == {}


@pytest.mark.parametrize(
    'fields',
    [
        [{'key': 'name', 'label': 'No', 'type': 'text'}],
        [{'key': 'a', 'label': 'No', 'type': 'text', 'show_if': {'field': 'a', 'equals': 'x'}}],
        [{'key': 'a', 'label': 'No', 'type': 'select', 'options': []}],
        [{'key': 'a', 'label': 'No', 'type': 'text'}, {'key': 'a', 'label': 'No', 'type': 'text'}],
    ],
)
def test_invalid_form_definitions_rejected(env, fields):
    client, d = env
    assert (
        client.patch('/api/v1/forms/' + d['form'].id, headers=d['headers'](), json={'fields': fields}).status_code
        == 422
    )


def setup_calendar(d, monkeypatch, **kwargs):
    monkeypatch.setattr(booking, 'now', lambda: datetime(2030, 1, 7, 12, tzinfo=timezone.utc))
    calendar = BookingCalendar(
        workspace_id=d['ws'].id,
        name='Reunião',
        assignee_id=d['owner'].id,
        lead_minutes=0,
        availability={str(i): [{'start': '09:00', 'end': '12:00'}] for i in range(7)},
        active=True,
        **kwargs,
    )
    db.session.add(calendar)
    db.session.commit()
    return calendar


def reserve_body():
    return dict(submit_body(), starts_at='2030-01-08T13:00:00+00:00')


def test_booking_idempotency_conflict_cancel_and_token_scope(env, monkeypatch):
    client, d = env
    calendar = setup_calendar(d, monkeypatch)
    path = '/api/v1/public/calendars/' + calendar.id
    slots = client.get(path + '/slots?date=2030-01-08')
    assert slots.status_code == 200 and '2030-01-08T13:00:00+00:00' in slots.json['items']
    body = reserve_body()
    response = client.post(path + '/book', json=body)
    assert response.status_code == 200, response.json
    token = response.json['token']
    assert client.post(path + '/book', json=body).status_code == 200
    assert Booking.query.count() == Activity.query.count() == Contact.query.count() == 1
    assert client.post(path + '/book', json=reserve_body()).status_code == 409
    assert client.get('/api/v1/bookings', headers=d['headers'](d['outsider'])).json['total'] == 0
    assert client.get('/api/v1/public/bookings/' + token + 'wrong').status_code == 404
    assert client.get('/api/v1/public/bookings/' + token).json['status'] == 'confirmed'
    assert client.post('/api/v1/public/bookings/' + token + '/cancel', json={}).status_code == 200
    assert Booking.query.one().status == Activity.query.one().status == 'cancelled'
    assert '2030-01-08T13:00:00+00:00' in client.get(path + '/slots?date=2030-01-08').json['items']


def test_booking_reschedule_rollback_and_shared_assignee(env, monkeypatch):
    client, d = env
    calendar = setup_calendar(d, monkeypatch, buffer_minutes=15)
    path = '/api/v1/public/calendars/' + calendar.id
    response = client.post(path + '/book', json=reserve_body())
    assert response.status_code == 200, response.json
    token = response.json['token']
    row = Booking.query.one()
    original = row.starts_at
    other = BookingCalendar(
        workspace_id=d['ws'].id,
        name='Outra',
        assignee_id=d['owner'].id,
        active=True,
        lead_minutes=0,
        availability=calendar.availability,
    )
    db.session.add(other)
    db.session.commit()
    assert client.post('/api/v1/public/calendars/' + other.id + '/book', json=reserve_body()).status_code == 409
    assert (
        client.post(
            '/api/v1/public/bookings/' + token + '/reschedule', json={'starts_at': '2030-01-08T12:00:00+00:00'}
        ).status_code
        == 409
    )
    db.session.refresh(row)
    assert row.status == 'confirmed' and row.starts_at == original
    new_time = '2030-01-08T13:45:00+00:00'
    assert (
        client.post('/api/v1/public/bookings/' + token + '/reschedule', json={'starts_at': new_time}).status_code == 200
    )
    assert (
        Booking.query.one().starts_at.isoformat() == new_time
        and Activity.query.one().scheduled_at.isoformat() == new_time
    )


def test_calendar_validation_pause_and_account_references(env, monkeypatch):
    client, d = env
    calendar = setup_calendar(d, monkeypatch)
    path = '/api/v1/booking-calendars/' + calendar.id
    assert client.patch(path, headers=d['headers'](d['member']), json={}).status_code == 403
    assert client.patch(path, headers=d['headers'](), json={'assignee_id': d['outsider'].id}).status_code == 404
    assert (
        client.patch(
            path,
            headers=d['headers'](),
            json={'availability': {'0': [{'start': '09:00', 'end': '12:00'}, {'start': '13:00', 'end': '18:00'}]}},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            path,
            headers=d['headers'](),
            json={'availability': {'0': [{'start': '09:00', 'end': '12:00'}, {'start': '11:00', 'end': '18:00'}]}},
        ).status_code
        == 422
    )
    assert client.patch(path, headers=d['headers'](), json={'active': False}).status_code == 200
    assert client.get('/api/v1/public/calendars/' + calendar.id).status_code == 404


def test_worker_heartbeat_and_operations_permissions(env):
    client, d = env
    assert client.get('/api/v1/operations/status', headers=d['headers'](d['member'])).status_code == 403
    assert client.get('/api/v1/operations/status', headers=d['headers']()).json['worker']['online'] is False
    headers = d['headers']()
    result = client.application.test_cli_runner().invoke(args=['run-worker', '--once'])
    assert result.exit_code == 0, result.output
    state = client.get('/api/v1/operations/status', headers=headers).json
    assert state['worker']['online'] and not state['worker']['dispatch_enabled']
    assert all('password' not in c and 'auth_token' not in c for c in state['channels'])


def test_suppression_prevents_enqueue_cancels_queue_and_is_scoped(env, monkeypatch):
    client, d = env
    contact = Contact(workspace_id=d['ws'].id, name='Lead', email='lead@example.test')
    db.session.add(contact)
    db.session.commit()
    message = enqueue(d['ws'].id, contact, 'email', 'hello', 'subject', str(uuid4()))
    db.session.commit()
    response = client.post(
        '/api/v1/communication-suppressions',
        headers=d['headers'](),
        json={'contact_id': contact.id, 'channel': 'email'},
    )
    assert response.status_code == 201, response.json
    assert message.status == 'cancelled'
    with pytest.raises(Exception):
        enqueue(d['ws'].id, contact, 'email', 'again', 'subject', str(uuid4()))
    assert client.get('/api/v1/communication-suppressions', headers=d['headers'](d['outsider'])).json['total'] == 0
    assert (
        client.delete('/api/v1/communication-suppressions/' + response.json['id'], headers=d['headers']()).status_code
        == 204
    )
    assert message.status == 'cancelled'


def test_conditions_snapshot_stop_on_reply_and_received_trigger(env):
    client, d = env
    response = client.post(
        '/api/v1/automations',
        headers=d['headers'](),
        json={
            'name': 'Retorno',
            'event': 'contact.created',
            'task_title': 'Task',
            'active': True,
            'stop_on_reply': True,
            'conditions': {'mode': 'all', 'items': [{'field': 'custom.valor', 'operator': 'gte', 'value': '100'}]},
            'actions': [{'kind': 'create_task', 'title': 'Telefonar', 'delay_minutes': 60}],
        },
    )
    assert response.status_code == 201, response.json
    assert (
        client.post(
            '/api/v1/contacts', headers=d['headers'](), json={'name': 'Small', 'custom_fields': {'valor': '50'}}
        ).status_code
        == 201
    )
    assert AutomationRun.query.count() == 0
    contact_response = client.post(
        '/api/v1/contacts', headers=d['headers'](), json={'name': 'Qualified', 'custom_fields': {'valor': '150'}}
    )
    assert contact_response.status_code == 201, contact_response.json
    run = AutomationRun.query.one()
    assert run.config_snapshot['stop_on_reply']
    assert (
        client.patch(
            '/api/v1/automations/' + response.json['id'], headers=d['headers'](), json={'stop_on_reply': False}
        ).status_code
        == 200
    )
    contact = db.session.get(Contact, contact_response.json['id'])
    received_reply(d['ws'].id, contact, str(uuid4()))
    db.session.commit()
    assert AutomationJob.query.one().status == 'cancelled' and run.status == 'cancelled'
    assert process(d['ws'].id) == []


def test_multiple_pipelines_keep_default_stages_and_isolate_accounts(env):
    client, d = env
    headers = d['headers']()
    response = client.post('/api/v1/pipelines', headers=headers, json={'name': 'Pós-venda'})
    assert response.status_code == 201, response.json
    pid = response.json['id']
    assert len(client.get('/api/v1/pipeline/stages?pipeline_id=' + pid, headers=headers).json['items']) == 4
    assert len(client.get('/api/v1/pipeline/stages?pipeline_id=default', headers=headers).json['items']) == 1
    assert (
        client.get('/api/v1/pipeline/stages?pipeline_id=' + pid, headers=d['headers'](d['outsider'])).status_code == 404
    )
    stage = client.get('/api/v1/pipeline/stages?pipeline_id=' + pid, headers=headers).json['items'][0]
    deal = {'title': 'Renewal', 'stage_id': stage['id']}
    assert client.post('/api/v1/opportunities', headers=headers, json=deal).status_code == 201
    assert client.get('/api/v1/opportunities?pipeline_id=' + pid, headers=headers).json['total'] == 1
    assert client.get('/api/v1/opportunities?pipeline_id=default', headers=headers).json['total'] == 0
    assert (
        client.post(
            '/api/v1/pipeline/stages', headers=headers, json={'name': stage['name'], 'pipeline_id': pid}
        ).status_code
        == 409
    )


def test_public_form_retry_after_definition_edit_returns_existing_success(env):
    client, d = env
    body = submit_body()
    path = '/api/v1/public/forms/' + d['form'].id + '/submit'
    assert client.post(path, json=body).status_code == 200
    d['form'].fields = [{'key': 'new', 'label': 'Nova pergunta', 'type': 'text', 'required': True}]
    db.session.commit()
    assert client.post(path, json=body).status_code == 200
    assert FormSubmission.query.count() == 1


def test_saved_views_are_private_to_account_and_user(env):
    client, d = env
    response = client.post(
        '/api/v1/contact-views', headers=d['headers'](), json={'name': 'Meus leads', 'filters': {'source': 'Site'}}
    )
    assert response.status_code == 201, response.json
    identifier = response.json['id']
    assert client.get('/api/v1/contact-views', headers=d['headers'](d['member'])).json['total'] == 0
    assert client.get('/api/v1/contact-views', headers=d['headers'](d['outsider'])).json['total'] == 0
    assert client.delete('/api/v1/contact-views/' + identifier, headers=d['headers'](d['member'])).status_code == 404
    assert (
        client.post(
            '/api/v1/contact-views', headers=d['headers'](), json={'name': 'meus leads', 'filters': {}}
        ).status_code
        == 409
    )
    assert client.get('/api/v1/contact-views', headers=d['headers']()).json['items'][0]['filters']['source'] == 'Site'


def test_stage_changed_automation_evaluates_new_stage(env):
    from app.models import PipelineStage, Task

    client, d = env
    headers = d['headers']()
    stage = PipelineStage(workspace_id=d['ws'].id, name='Proposta', position=1)
    contact = Contact(workspace_id=d['ws'].id, name='Lead')
    db.session.add_all([stage, contact])
    db.session.commit()
    rule_response = client.post(
        '/api/v1/automations',
        headers=headers,
        json={
            'name': 'Proposta',
            'event': 'opportunity.stage_changed',
            'task_title': 'Enviar proposta',
            'active': True,
            'conditions': {
                'mode': 'all',
                'items': [{'field': 'deal.stage_id', 'operator': 'equals', 'value': stage.id}],
            },
        },
    )
    assert rule_response.status_code == 201, rule_response.json
    deal = client.post(
        '/api/v1/opportunities',
        headers=headers,
        json={'title': 'Venda', 'stage_id': d['stage'].id, 'contact_id': contact.id},
    ).json
    assert (
        client.patch('/api/v1/opportunities/' + deal['id'], headers=headers, json={'stage_id': stage.id}).status_code
        == 200
    )
    assert Task.query.one().title == 'Enviar proposta'


def test_inbound_message_cancels_queued_automation_message(env):
    import hashlib
    import hmac
    import json
    import time
    from test_communications import setup_channel
    from app.services.automations import emit

    client, d = env
    contact, template = setup_channel(client, d)
    rule(
        d,
        event='contact.created',
        stop_on_reply=True,
        actions=[
            {'kind': 'send_message', 'template_id': template.id},
            {'kind': 'create_task', 'title': 'Ligar', 'delay_minutes': 60},
        ],
    )
    emit(d['ws'].id, 'contact.created', contact.id, contact)
    db.session.commit()
    process(d['ws'].id)
    assert InboxMessage.query.one().status == 'queued'
    content = json.dumps({'provider_id': 'reply-1', 'address': contact.email, 'content': 'Já respondi'})
    timestamp = str(int(time.time()))
    signature = hmac.new(
        b'test-inbound-secret', timestamp.encode() + b'.' + content.encode(), hashlib.sha256
    ).hexdigest()
    response = client.post(
        '/api/v1/communications/receive/' + d['ws'].id + '/email',
        data=content,
        headers={'Content-Type': 'application/json', 'X-Timestamp': timestamp, 'X-Signature': signature},
    )
    assert response.status_code == 201, response.json
    assert InboxMessage.query.filter_by(direction='out').one().status == 'cancelled'
    assert AutomationJob.query.filter_by(position=1).one().status == 'cancelled'
    assert AutomationRun.query.one().status == 'cancelled'


def test_calendar_shows_each_booking_once_and_tracks_reschedule_and_cancel(env, monkeypatch):
    client, d = env
    calendar = setup_calendar(d, monkeypatch)
    booked = client.post('/api/v1/public/calendars/' + calendar.id + '/book', json=reserve_body())
    assert booked.status_code == 200
    path = '/api/v1/calendar?start=2030-01-01&end=2030-01-31'
    events = client.get(path, headers=d['headers']()).json['items']
    assert len(events) == 1
    assert events[0]['booking_id'] == Booking.query.one().id
    assert events[0]['contact_name'] == 'Lead de teste'
    assert events[0]['ends_at'] is not None
    assert client.get(path, headers=d['headers'](d['outsider'])).json['items'] == []
    token = booked.json['token']
    changed = client.post(
        '/api/v1/public/bookings/' + token + '/reschedule', json={'starts_at': '2030-01-08T14:00:00+00:00'}
    )
    assert changed.status_code == 200
    events = client.get(path, headers=d['headers']()).json['items']
    assert len(events) == 1 and events[0]['date'].startswith('2030-01-08T14:00:00')
    assert client.post('/api/v1/public/bookings/' + token + '/cancel', json={}).status_code == 200
    assert client.get(path, headers=d['headers']()).json['items'] == []
