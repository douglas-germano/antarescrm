from datetime import timedelta

from app.extensions import db
from app.models import Contact, InboxMessage, InboxThread, WhatsAppConversation, WhatsAppMessage, now
from test_reports_overview import seed


def contact(ws, name, source, **extra):
    row = Contact(workspace_id=ws, name=name, source=source, **extra)
    db.session.add(row)
    db.session.flush()
    return row


def message(ws, thread, direction, key, at, status='received'):
    return InboxMessage(
        workspace_id=ws,
        thread_id=thread.id,
        direction=direction,
        content='-',
        status=status,
        idempotency_key=key,
        created_at=at,
    )


def conversations(d):
    """Instagram talk with A answered in 1 h; WhatsApp talk with B answered in 9 min after a failed reply."""
    ws = d['ws'].id
    by_name = {c.name: c for c in Contact.query.filter_by(workspace_id=ws).all()}
    ig = InboxThread(workspace_id=ws, channel='instagram', address='1:2', contact_id=by_name['A'].id)
    wa = WhatsAppConversation(workspace_id=ws, phone='5565999900001', contact_id=by_name['B'].id, last_message_at=now())
    old = InboxThread(workspace_id=ws, channel='email', address='old@example.com')
    db.session.add_all([ig, wa, old])
    db.session.flush()
    at = now()
    long_ago = at - timedelta(days=40)
    db.session.add_all(
        [
            message(ws, ig, 'in', '1', at - timedelta(hours=3)),
            message(ws, ig, 'out', '2', at - timedelta(hours=2), 'sent'),
            WhatsAppMessage(
                workspace_id=ws,
                conversation_id=wa.id,
                direction='in',
                content='?',
                occurred_at=at - timedelta(minutes=10),
            ),
            WhatsAppMessage(
                workspace_id=ws,
                conversation_id=wa.id,
                direction='out',
                content='x',
                status='failed',
                occurred_at=at - timedelta(minutes=5),
            ),
            WhatsAppMessage(
                workspace_id=ws,
                conversation_id=wa.id,
                direction='out',
                content='ok',
                status='sent',
                occurred_at=at - timedelta(minutes=1),
            ),
            # Previous period: one answer after 30 minutes.
            message(ws, old, 'in', '3', long_ago),
            message(ws, old, 'out', '4', long_ago + timedelta(minutes=30), 'sent'),
        ]
    )


def test_journey_follows_new_contacts_by_origin_to_conversation_deal_and_sale(env):
    client, d = env
    seed(d)  # A (Instagram, won R$ 1.000) and B (Indicação, one lost and one open deal).
    ws = d['ws'].id
    contact(ws, 'C', 'Instagram')  # Arrived, never talked, no deal.
    contact(ws, 'Antigo', 'Instagram', created_at=now() - timedelta(days=90))  # Outside the period.
    conversations(d)
    db.session.commit()

    journey = client.get('/api/v1/reports/overview', headers=d['headers']()).get_json()['journey']
    rows = {r['source']: r for r in journey['items']}
    assert [r['source'] for r in journey['items']] == ['Instagram', 'Indicação']
    assert rows['Instagram'] == {
        'source': 'Instagram',
        'contacts': 2,
        'conversation': 1,
        'deal': 1,
        'won': 1,
        'won_amount': 1000.0,
        'won_rate': 50.0,
    }
    assert rows['Indicação'] == {
        'source': 'Indicação',
        'contacts': 1,
        'conversation': 1,
        'deal': 1,
        'won': 0,
        'won_amount': 0.0,
        'won_rate': 0.0,
    }
    total = journey['total']
    assert (total['contacts'], total['conversation'], total['deal'], total['won'], total['won_rate']) == (
        3,
        2,
        2,
        1,
        33.3,
    )


def test_first_response_median_in_the_period_and_the_previous_one(env):
    client, d = env
    seed(d)
    conversations(d)
    db.session.commit()
    first = client.get('/api/v1/reports/overview', headers=d['headers']()).get_json()['first_response']
    # 3600 s on Instagram and 540 s on WhatsApp: the failed reply does not end the wait.
    assert first['current'] == {'median_seconds': 2070, 'sample': 2}
    assert first['previous'] == {'median_seconds': 1800, 'sample': 1}
    assert first['unit'] == 'seconds'


def test_journey_and_first_response_stay_inside_the_account(env):
    client, d = env
    seed(d)
    conversations(d)
    db.session.commit()
    data = client.get('/api/v1/reports/overview', headers=d['headers'](d['outsider'])).get_json()
    assert data['journey']['items'] == [] and data['journey']['total']['contacts'] == 0
    assert data['first_response']['current'] == {'median_seconds': None, 'sample': 0}
