from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models import (
    AutomationJob,
    AutomationRun,
    InboxMessage,
    InboxThread,
    PipelineStage,
    Task,
    WhatsAppConversation,
    WhatsAppMessage,
)
from app.services import automations
from helpers.automations import contact_for


def create_rule(client, headers, event, actions, **extra):
    body = {'name': 'Fluxo', 'task_title': 'Fluxo', 'event': event, 'active': True, 'actions': actions, **extra}
    response = client.post('/api/v1/automations', headers=headers, json=body)
    assert response.status_code == 201, response.json
    return body


def create_deal(client, d, contact):
    response = client.post(
        '/api/v1/opportunities',
        headers=d['headers'](),
        json={'title': 'Negócio', 'stage_id': d['stage'].id, 'contact_id': contact.id, 'owner_id': d['owner'].id},
    )
    assert response.status_code == 201, response.json
    return response.json


@pytest.mark.parametrize('channel', ['inbox', 'native', 'other'])
def test_wait_reply_selects_one_path_and_preview_has_no_effects(env, monkeypatch, channel):
    client, d = env
    headers = d['headers']()
    clock = datetime(2030, 1, 7, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(automations, 'now', lambda: clock)
    contact = contact_for(d)
    whatsapp = InboxThread(workspace_id=d['ws'].id, contact_id=contact.id, channel='whatsapp', address='5565999999999')
    instagram = InboxThread(workspace_id=d['ws'].id, contact_id=contact.id, channel='instagram', address='1234')
    native = WhatsAppConversation(workspace_id=d['ws'].id, contact_id=contact.id, phone='5565999999999')
    db.session.add_all([native if channel == 'native' else whatsapp, instagram])
    db.session.commit()
    body = create_rule(
        client,
        headers,
        'opportunity.created',
        [
            {
                'kind': 'branch',
                'wait_reply_minutes': 3,
                'reply_channel': 'whatsapp',
                'yes': [{'kind': 'create_task', 'title': 'Respondeu'}],
                'no': [{'kind': 'create_task', 'title': 'Retomar', 'assign_deal_owner': True}],
            }
        ],
    )
    deal = create_deal(client, d, contact)
    preview = client.post(
        '/api/v1/automations/preview',
        headers=headers,
        json={'rule': body, 'opportunity_id': deal['id'], 'reply_received': True},
    )
    assert preview.status_code == 200, preview.json
    assert preview.json['steps'][1]['title'] == 'Respondeu'
    assert Task.query.count() == 0 and AutomationJob.query.count() == 1
    assert automations.process()[0]['status'] == 'pending'
    correct_thread = channel != 'other'
    if channel == 'native':
        db.session.add(
            WhatsAppMessage(
                workspace_id=d['ws'].id,
                conversation_id=native.id,
                direction='in',
                content='Oi',
                occurred_at=clock + timedelta(seconds=20),
                created_at=clock + timedelta(seconds=20),
            )
        )
    else:
        db.session.add(
            InboxMessage(
                workspace_id=d['ws'].id,
                thread_id=whatsapp.id if correct_thread else instagram.id,
                direction='in',
                status='received',
                content='Oi',
                idempotency_key='reply',
                created_at=clock + timedelta(seconds=20),
            )
        )
    db.session.commit()
    clock += timedelta(minutes=1 if correct_thread else 3)
    automations.process()
    automations.process()
    assert Task.query.one().title == ('Respondeu' if correct_thread else 'Retomar')
    if not correct_thread:
        assert Task.query.one().assignee_id == d['owner'].id
    assert AutomationRun.query.one().status == 'completed'


def test_stage_idle_revalidates_entry_and_task_completion_emits_once(env, monkeypatch):
    client, d = env
    headers = d['headers']()
    clock = datetime(2030, 1, 7, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(automations, 'now', lambda: clock)
    contact = contact_for(d)
    other = PipelineStage(workspace_id=d['ws'].id, name='Proposta', position=10)
    db.session.add(other)
    db.session.commit()
    create_rule(
        client, headers, 'opportunity.stage_idle', [{'kind': 'create_task', 'title': 'Revisar', 'stage_days': 2}]
    )
    create_rule(client, headers, 'task.completed', [{'kind': 'create_task', 'title': 'Próxima'}])
    deal = create_deal(client, d, contact)
    clock += timedelta(days=1)
    assert (
        client.patch('/api/v1/opportunities/' + deal['id'], headers=headers, json={'stage_id': other.id}).status_code
        == 200
    )
    clock += timedelta(days=1)
    assert automations.process()[0]['status'] == 'skipped'
    clock += timedelta(days=1)
    assert automations.process()[0]['status'] == 'completed'
    task_path = '/api/v1/tasks/' + Task.query.one().id
    for _ in range(2):
        assert client.patch(task_path, headers=headers, json={'status': 'done'}).status_code == 200
    automations.process()
    assert Task.query.filter_by(title='Próxima').count() == 1
