from datetime import timedelta
from uuid import uuid4

from test_growth import env
from test_whatsapp_service import raw
from test_instagram import configure_instagram, event, receive
from app.extensions import db
from app.models import (
    Contact,
    InboxMessage,
    InboxThread,
    MessageNotification,
    NotificationReadState,
    WhatsAppMessage,
    now,
)
from app.services import notifications, whatsapp, instagram


def notice(d, channel='email', workspace=None, thread=None, content='Nova mensagem'):
    wid = workspace or d['ws'].id
    thread = thread or InboxThread(workspace_id=wid, channel=channel, address=str(uuid4()) + '@example.test')
    db.session.add(thread)
    db.session.flush()
    message = InboxMessage(
        workspace_id=wid,
        thread_id=thread.id,
        direction='in',
        status='received',
        content=content,
        idempotency_key=str(uuid4()),
    )
    db.session.add(message)
    db.session.flush()
    notifications.record(thread, message, 'inbox')
    db.session.commit()
    return thread, message


def feed(client, d, user=None):
    result = client.get('/api/v1/inbox/notifications', headers=d['headers'](user or d['owner']))
    assert result.status_code == 200, result.json
    return result.json


def mark(client, d, thread, message, user=None):
    return client.post(
        '/api/v1/inbox/notifications/read',
        headers=d['headers'](user or d['owner']),
        json={'source': 'inbox', 'thread_id': thread.id, 'message_id': message.id},
    )


def test_feed_groups_conversations_and_read_state_is_per_user_and_account(env):
    client, d = env
    assert feed(client, d)['cursor'] is None
    thread, first = notice(d)
    _, second = notice(d, thread=thread)
    other, _ = notice(d, 'instagram')
    notice(d, workspace=d['other'].id, content='Private')
    body = feed(client, d)
    assert body['total_unread'] == 3 and body['unread_threads'] == 2
    assert len(body['items']) == 2 and sorted(row['unread_count'] for row in body['items']) == [1, 2]
    assert all(row['preview'] != 'Private' for row in body['items'])
    assert mark(client, d, thread, first).status_code == 200
    assert feed(client, d)['total_unread'] == 2
    assert feed(client, d, d['member'])['total_unread'] == 3
    assert mark(client, d, thread, second).status_code == 200
    assert feed(client, d)['total_unread'] == 1
    assert feed(client, d, d['outsider'])['total_unread'] == 1
    assert client.post('/api/v1/inbox/notifications/read-all', headers=d['headers'](), json={}).status_code == 200
    assert feed(client, d)['total_unread'] == 0
    assert feed(client, d, d['member'])['total_unread'] == 3
    assert NotificationReadState.query.filter_by(user_id=d['owner'].id).count() == 2


def test_read_cursor_is_monotonic_and_does_not_acknowledge_later_messages(env):
    client, d = env
    thread, first = notice(d)
    _, second = notice(d, thread=thread)
    mark(client, d, thread, second)
    mark(client, d, thread, first)
    assert feed(client, d)['total_unread'] == 0
    _, third = notice(d, thread=thread)
    mark(client, d, thread, second)
    assert feed(client, d)['total_unread'] == 1
    assert feed(client, d)['items'][0]['message_id'] == third.id


def test_notifications_are_bounded_and_unread_totals_cover_all_conversations(env):
    client, d = env
    for _ in range(25):
        notice(d)
    body = feed(client, d)
    assert len(body['items']) == 20 and body['total_unread'] == body['unread_threads'] == 25
    client.post('/api/v1/inbox/notifications/read-all', headers=d['headers'](), json={})
    assert feed(client, d)['total_unread'] == 0


def test_whatsapp_live_receives_notify_once_but_history_and_outgoing_do_not(env):
    client, d = env
    connection = whatsapp.connection_for(d['ws'].id)
    incoming, _ = whatsapp.ingest(connection, raw('incoming'))
    whatsapp.ingest(connection, raw('incoming'))
    whatsapp.ingest(connection, raw('history', timestamp=int((now() - timedelta(days=5)).timestamp())), historical=True)
    whatsapp.ingest(connection, raw('own-app-echo', outgoing=True))
    db.session.commit()
    assert MessageNotification.query.count() == 1
    body = feed(client, d)
    assert body['items'][0]['source'] == 'whatsapp' and body['items'][0]['message_id'] == incoming.id
    result = client.post(
        '/api/v1/inbox/notifications/read',
        headers=d['headers'](),
        json={'source': 'whatsapp', 'thread_id': incoming.conversation_id, 'message_id': incoming.id},
    )
    assert result.status_code == 200 and feed(client, d)['total_unread'] == 0
    detail = client.get(f'/api/v1/inbox/whatsapp/{incoming.conversation_id}', headers=d['headers']())
    assert detail.status_code == 200 and detail.json['source'] == 'whatsapp'


def test_instagram_received_dms_notify_once_and_echoes_do_not(env, monkeypatch):
    client, d = env
    monkeypatch.setattr(instagram, 'fetch_profile', lambda *args: None)
    configure_instagram(client, d)
    for _ in range(2):
        assert receive(client, event()).status_code == 200
    assert MessageNotification.query.count() == 1
    body = event('own-echo')
    item = body['entry'][0]['messaging'][0]
    item['sender'], item['recipient'] = item['recipient'], item['sender']
    assert receive(client, body).status_code == 200
    assert MessageNotification.query.count() == 1
    assert feed(client, d)['items'][0]['channel'] == 'instagram'


def test_scope_validation_and_unknown_old_messages_do_not_mark_future_notifications(env):
    client, d = env
    thread, first = notice(d)
    assert mark(client, d, thread, first, d['outsider']).status_code == 404
    assert client.get(f'/api/v1/inbox/inbox/{thread.id}', headers=d['headers'](d['outsider'])).status_code == 404
    assert client.get(f'/api/v1/inbox/invalid/{thread.id}', headers=d['headers']()).status_code == 404
    assert client.get('/api/v1/inbox/notifications').status_code == 401
    assert client.post('/api/v1/inbox/notifications/read', headers=d['headers'](), json={}).status_code == 422
    old = InboxMessage(
        workspace_id=d['ws'].id,
        thread_id=thread.id,
        direction='in',
        status='received',
        content='Old history',
        idempotency_key=str(uuid4()),
    )
    db.session.add(old)
    db.session.commit()
    assert mark(client, d, thread, old).status_code == 200
    assert feed(client, d)['total_unread'] == 1


def test_inbox_uses_each_users_new_notification_counts(env):
    client, d = env
    thread, message = notice(d, 'instagram')

    def count(user=None):
        result = client.get('/api/v1/inbox', headers=d['headers'](user or d['owner']))
        return next(row['unread_count'] for row in result.json['items'] if row['id'] == thread.id)

    assert count() == 1 and count(d['member']) == 1
    mark(client, d, thread, message)
    assert count() == 0 and count(d['member']) == 1
