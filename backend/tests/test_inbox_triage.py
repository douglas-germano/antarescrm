from datetime import timedelta

from app.extensions import db
from app.models import Contact, InboxMessage, InboxThread, Opportunity, WhatsAppConversation, WhatsAppMessage, now


def seed(d):
    ws = d['ws'].id
    buyer = Contact(workspace_id=ws, name='Compradora', custom_fields={'instagram_username': 'compradora'})
    db.session.add(buyer)
    db.session.flush()
    db.session.add(Opportunity(workspace_id=ws, title='Venda', contact_id=buyer.id, stage_id=d['stage'].id, amount=100))
    ig = InboxThread(workspace_id=ws, channel='instagram', address='1234:5678', contact_id=buyer.id)
    wa = WhatsAppConversation(workspace_id=ws, phone='5565999900001', contact_name='Zap', last_message_at=now())
    db.session.add_all([ig, wa])
    db.session.flush()
    db.session.add_all(
        [
            InboxMessage(
                workspace_id=ws,
                thread_id=ig.id,
                direction='in',
                content='Oi',
                idempotency_key='a',
                created_at=now() - timedelta(hours=2),
            ),
            WhatsAppMessage(
                workspace_id=ws,
                conversation_id=wa.id,
                direction='in',
                content='1',
                occurred_at=now() - timedelta(minutes=5),
            ),
            WhatsAppMessage(workspace_id=ws, conversation_id=wa.id, direction='out', content='2', occurred_at=now()),
        ]
    )
    db.session.commit()
    return ig, wa


def test_list_carries_owner_status_window_deal_and_last_direction(env):
    client, d = env
    ig, wa = seed(d)
    items = {i['channel']: i for i in client.get('/api/v1/inbox', headers=d['headers']()).json['items']}
    assert items['instagram']['status'] == 'open' and items['instagram']['assigned_to_id'] is None
    assert items['instagram']['has_open_deal'] and items['instagram']['display_address'] == '@compradora'
    assert items['instagram']['last_direction'] == 'in' and items['instagram']['last_inbound_at']
    assert items['whatsapp']['last_direction'] == 'out' and not items['whatsapp']['has_open_deal']


def test_instagram_threads_can_be_closed_and_assigned(env):
    client, d = env
    ig, _ = seed(d)
    patch = lambda body, user=None: client.patch(  # noqa: E731
        f'/api/v1/inbox/inbox/{ig.id}', headers=d['headers'](user or d['owner']), json=body
    )
    assert patch({'status': 'closed', 'assigned_to_id': d['member'].id}).status_code == 200
    row = db.session.get(InboxThread, ig.id)
    assert row.status == 'closed' and row.assigned_to_id == d['member'].id
    assert patch({'assigned_to_id': d['outsider'].id}).status_code == 404  # Someone from another account.
    assert patch({'status': 'archived'}).status_code == 422
    assert (
        client.patch(
            f'/api/v1/inbox/inbox/{ig.id}', headers=d['headers'](d['outsider']), json={'status': 'open'}
        ).status_code
        == 404
    )


def test_a_new_instagram_message_reopens_a_closed_conversation(env):
    from helpers.instagram import configure_instagram, event, receive

    client, d = env
    configure_instagram(client, d)
    receive(client, event('m1'))
    thread = InboxThread.query.one()
    thread.status = 'closed'
    db.session.commit()
    receive(client, event('m2'))
    assert db.session.get(InboxThread, thread.id).status == 'open'
