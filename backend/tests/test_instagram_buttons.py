from datetime import timedelta

from app.extensions import db
from app.models import AutomationJob, AutomationRule, AutomationRun, Contact, InboxMessage, now
from app.services.automations import process
from app.services.instagram import client as instagram_client
from helpers.instagram import comment_event, comment_rule, configure_instagram, receive

BUTTONS = [{'title': 'Ver proposta', 'url': 'https://exemplo.com/proposta'}]
REPLIES = ['Sim, quero', 'Agora não']
BASE = {'name': 'Fluxo', 'event': 'message.received', 'task_title': 'Fallback', 'due_days': 0}


def dm(mid, text, hours_ago=0):
    return {
        'object': 'instagram',
        'entry': [
            {
                'id': '1234',
                'messaging': [
                    {
                        'sender': {'id': '5678'},
                        'recipient': {'id': '1234'},
                        'timestamp': int((now() - timedelta(hours=hours_ago)).timestamp() * 1000),
                        'message': {'mid': mid, 'text': text},
                    }
                ],
            }
        ],
    }


def capture(monkeypatch):
    calls = []

    def graph(path, token, method='GET', **kwargs):
        calls.append((path, kwargs))
        return {'id': 'r1', 'message_id': 'dm' + str(len(calls))}

    monkeypatch.setattr(instagram_client, 'graph', graph)
    return calls


def test_private_reply_sends_link_buttons_and_quick_replies(env, monkeypatch):
    client, d = env
    configure_instagram(client, d)
    comment_rule(
        d,
        [{'kind': 'private_reply', 'content': 'Oi!', 'buttons': BUTTONS, 'quick_replies': REPLIES, 'delay_minutes': 0}],
    )
    calls = capture(monkeypatch)
    receive(client, comment_event())
    process(d['ws'].id)
    message = calls[0][1]['json']['message']
    assert message['attachment']['payload'] == {
        'template_type': 'button',
        'text': 'Oi!',
        'buttons': [{'type': 'web_url', 'url': 'https://exemplo.com/proposta', 'title': 'Ver proposta'}],
    }
    assert [q['title'] for q in message['quick_replies']] == REPLIES
    stored = InboxMessage.query.filter_by(direction='out').one().content
    assert 'Ver proposta (https://exemplo.com/proposta)' in stored and 'Sim, quero · Agora não' in stored


def test_quick_reply_answer_drives_the_branch(env, monkeypatch):
    client, d = env
    configure_instagram(client, d)
    reply_is = lambda value: {'mode': 'all', 'items': [{'field': 'reply.text', 'operator': 'equals', 'value': value}]}  # noqa: E731
    db.session.add(
        AutomationRule(
            workspace_id=d['ws'].id,
            name='Qualificar',
            event='message.received',
            task_title='t',
            active=True,
            # The trigger reads the incoming message too, so the answer itself does not restart the flow.
            conditions={'mode': 'all', 'items': [{'field': 'reply.text', 'operator': 'contains', 'value': 'preço'}]},
            actions=[
                {'kind': 'instagram_message', 'content': 'Quer receber?', 'quick_replies': REPLIES, 'delay_minutes': 0},
                {
                    'kind': 'branch',
                    'conditions': reply_is('Sim, quero'),
                    'delay_minutes': 60,
                    'yes': [{'kind': 'add_tag', 'tag': 'interessado', 'delay_minutes': 0}],
                    'no': [{'kind': 'add_tag', 'tag': 'frio', 'delay_minutes': 0}],
                },
            ],
        )
    )
    db.session.commit()
    calls = capture(monkeypatch)
    receive(client, dm('m1', 'Qual o preço?'))
    process(d['ws'].id)
    assert calls[0][1]['json']['recipient'] == {'id': '5678'}
    assert [q['title'] for q in calls[0][1]['json']['message']['quick_replies']] == REPLIES
    receive(client, dm('m2', 'Sim, quero'))  # Tapping a quick reply arrives as the contact's message.
    assert AutomationRun.query.count() == 1
    sent, branch = AutomationJob.query.order_by(AutomationJob.position).all()
    branch.scheduled_at = sent.scheduled_at  # Skip the hour of waiting.
    db.session.commit()
    process(d['ws'].id)
    assert Contact.query.one().tags == ['interessado']
    assert AutomationRun.query.one().status == 'completed'


def test_direct_message_is_dismissed_outside_the_24_hour_window(env, monkeypatch):
    client, d = env
    configure_instagram(client, d)
    receive(client, dm('old', 'Oi', hours_ago=30))
    contact = Contact.query.one()
    from app.services.automations import emit

    db.session.add(
        AutomationRule(
            workspace_id=d['ws'].id,
            name='Direct',
            event='contact.created',
            task_title='t',
            active=True,
            actions=[{'kind': 'instagram_message', 'content': 'Oi', 'buttons': BUTTONS, 'delay_minutes': 0}],
        )
    )
    db.session.commit()
    calls = capture(monkeypatch)
    emit(d['ws'].id, 'contact.created', 'manual-1', contact)
    db.session.commit()
    process(d['ws'].id)
    assert calls == []
    assert 'dispensada' in AutomationJob.query.one().detail


def test_button_validation(env):
    client, d = env
    post = lambda actions: client.post(  # noqa: E731
        '/api/v1/automations', headers=d['headers'](), json={**BASE, 'actions': actions}
    )
    dm_step = lambda **kw: {'kind': 'instagram_message', 'content': 'Oi', 'delay_minutes': 0, **kw}  # noqa: E731
    assert post([dm_step(buttons=[{'title': 'Site', 'url': 'http://inseguro.com'}])]).status_code == 422
    assert post([dm_step(buttons=BUTTONS * 4)]).status_code == 422
    assert post([dm_step(quick_replies=['Sim', 'Sim'])]).status_code == 422
    assert post([dm_step(quick_replies=['Uma resposta longa demais'])]).status_code == 422
    assert post([dm_step(content='x' * 700, buttons=BUTTONS)]).status_code == 422
    assert post([{'kind': 'instagram_message', 'delay_minutes': 0}]).status_code == 422
    saved = post([dm_step(buttons=BUTTONS, quick_replies=REPLIES), {'kind': 'add_tag', 'tag': 'x', 'buttons': BUTTONS}])
    assert saved.status_code == 201
    first, second = db.session.get(AutomationRule, saved.json['id']).actions
    assert first['buttons'] == BUTTONS and first['quick_replies'] == REPLIES
    assert 'buttons' not in second  # Only Instagram direct messages carry buttons.
