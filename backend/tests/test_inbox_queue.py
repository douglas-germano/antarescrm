from datetime import timedelta

from app.extensions import db
from app.models import InboxMessage, InboxThread, WhatsAppConversation, WhatsAppMessage, now
from test_inbox_triage import seed


def test_list_says_who_waits_since_when_and_who_owns_it(env):
    client, d = env
    ig, wa = seed(d)
    ig.assigned_to_id = d['member'].id
    db.session.commit()
    items = {i['channel']: i for i in client.get('/api/v1/inbox', headers=d['headers']()).json['items']}
    assert items['instagram']['waiting_on'] == 'team' and items['instagram']['waiting_since']
    assert items['instagram']['assigned_to_name'] == 'Member'
    assert items['whatsapp']['waiting_on'] == 'contact' and items['whatsapp']['waiting_since'] is None
    assert items['whatsapp']['assigned_to_name'] is None
    assert not items['instagram']['delivery_failed'] and not items['whatsapp']['delivery_failed']


def test_waiting_starts_at_the_first_message_after_the_last_reply(env):
    client, d = env
    ws = d['ws'].id
    thread = InboxThread(workspace_id=ws, channel='email', address='a@example.com')
    db.session.add(thread)
    db.session.flush()
    for key, direction, minutes in (('1', 'in', 90), ('2', 'out', 60), ('3', 'in', 30), ('4', 'in', 10)):
        db.session.add(
            InboxMessage(
                workspace_id=ws,
                thread_id=thread.id,
                direction=direction,
                content=key,
                status='sent' if direction == 'out' else 'received',
                idempotency_key=key,
                created_at=now() - timedelta(minutes=minutes),
            )
        )
    db.session.commit()
    item = client.get('/api/v1/inbox', headers=d['headers']()).json['items'][0]
    since = InboxMessage.query.filter_by(idempotency_key='3').one().created_at
    assert item['preview'] == '4' and item['waiting_since'] == since.isoformat()


def test_failed_last_reply_is_flagged_with_its_error(env):
    client, d = env
    ig, wa = seed(d)
    db.session.add_all(
        [
            InboxMessage(
                workspace_id=d['ws'].id,
                thread_id=ig.id,
                direction='out',
                content='Resposta',
                status='blocked',
                error='Janela de 24 horas encerrada.',
                idempotency_key='b',
            ),
            WhatsAppMessage(
                workspace_id=d['ws'].id,
                conversation_id=wa.id,
                direction='out',
                content='3',
                status='pending',
                occurred_at=now() + timedelta(seconds=1),
            ),
        ]
    )
    db.session.commit()
    items = {i['channel']: i for i in client.get('/api/v1/inbox', headers=d['headers']()).json['items']}
    assert (
        items['instagram']['delivery_failed']
        and items['instagram']['delivery_error'] == 'Janela de 24 horas encerrada.'
    )
    assert not items['whatsapp']['delivery_failed']  # Still pending is not a failure.


def test_summary_counts_open_conversations_and_median_first_response(env):
    client, d = env
    ig, wa = seed(d)
    ws = d['ws'].id
    wa.assigned_to_id = d['owner'].id
    closed = WhatsAppConversation(workspace_id=ws, phone='5565999900002', status='closed', last_message_at=now())
    db.session.add(closed)
    db.session.flush()
    db.session.add_all(
        [
            WhatsAppMessage(workspace_id=ws, conversation_id=closed.id, direction='out', content='x', status='unknown'),
            InboxMessage(
                workspace_id=ws,
                thread_id=ig.id,
                direction='out',
                content='Oi!',
                status='sent',
                idempotency_key='r',
                created_at=now() - timedelta(hours=1),
            ),
            InboxMessage(
                workspace_id=ws,
                thread_id=ig.id,
                direction='in',
                content='Preço?',
                idempotency_key='q',
                created_at=now() - timedelta(minutes=20),
            ),
        ]
    )
    db.session.commit()
    body = client.get('/api/v1/inbox/summary', headers=d['headers']()).json
    assert body['open'] == 2 and body['mine'] == 1 and body['unassigned'] == 1
    assert body['waiting_team'] == 1 and body['delivery_failed'] == 0  # The failed one is closed.
    # Instagram answered in 1 h; WhatsApp in 5 min.
    assert body['first_response_sample'] == 2 and body['first_response_median'] == 1950
    assert body['period_days'] == 7 and body['unit'] == 'seconds'
    other = client.get('/api/v1/inbox/summary', headers=d['headers'](d['outsider'])).json
    assert other['open'] == 0 and other['first_response_sample'] == 0 and other['first_response_median'] is None
