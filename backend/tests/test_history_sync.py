"""History imports must be resumable, tenant scoped and never trigger outbound work."""

from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock

import pytest
from test_growth import env
from test_instagram import configure_instagram
from test_whatsapp_service import raw

from app.common import APIError
from app.extensions import db
from app.models import (
    AutomationRule,
    AutomationRun,
    HistorySync,
    InboxMessage,
    InboxThread,
    MessageNotification,
    WhatsAppConversation,
    WhatsAppMessage,
    now,
)
from app.services import history, instagram, whatsapp


def control(client, d, channel='whatsapp', action='start', user=None):
    return client.post(
        '/api/v1/history-sync/' + channel, headers=d['headers'](user or d['owner']), json={'action': action}
    )


def page_provider(monkeypatch, pages):
    def page(connection, number):
        return deepcopy(pages.get(number, [])), sum(len(rows) for rows in pages.values())

    monkeypatch.setattr(history, 'messages_page', page)


def drain(maximum=20):
    for _ in range(maximum):
        if not history.process():
            return
    pytest.fail('Import did not terminate')


def test_whatsapp_two_pass_mapping_silent_import_and_rerun(env, monkeypatch):
    client, d = env
    whatsapp.connection_for(d['ws'].id)
    db.session.add_all(
        [
            AutomationRule(
                workspace_id=d['ws'].id,
                name='No historical alerts',
                event=event,
                active=True,
                task_title='Must not run',
                due_days=0,
            )
            for event in ('contact.created', 'message.received')
        ]
    )
    db.session.commit()
    old = raw('old', timestamp=int((now() - timedelta(days=30)).timestamp()))
    lid = {**old, 'key': {**old['key'], 'remoteJid': '999@lid'}}
    mapping = raw('mapping', outgoing=True)
    mapping['key']['remoteJidAlt'] = '999@lid'
    unknown = raw('unresolved')
    unknown['key']['remoteJid'] = '888@lid'
    group = raw('group')
    group['key']['remoteJid'] = '123@g.us'
    # Mapping arrives on a later page; the earlier LID record must still import.
    page_provider(monkeypatch, {1: [lid, unknown, group], 2: [mapping]})
    assert control(client, d).status_code == 200
    drain()
    job = HistorySync.query.one()
    assert (job.status, job.imported, job.skipped, job.unresolved) == ('completed', 2, 2, 1)
    assert WhatsAppMessage.query.count() == 2
    assert WhatsAppConversation.query.one().unread_count == 0
    assert AutomationRun.query.count() == MessageNotification.query.count() == 0
    assert min(m.occurred_at for m in WhatsAppMessage.query.all()) == old_date(old)
    assert control(client, d).status_code == 200
    drain()
    assert job.imported == 0 and job.duplicates == 2 and WhatsAppMessage.query.count() == 2


def old_date(message):
    from datetime import datetime, timezone

    return datetime.fromtimestamp(message['messageTimestamp'], timezone.utc)


def test_pause_resume_errors_and_checkpoint_rollback(env, monkeypatch):
    client, d = env
    whatsapp.connection_for(d['ws'].id)
    page_provider(monkeypatch, {1: [raw('one'), raw('two')]})
    control(client, d)
    history.process()
    history.process()  # discovery and end marker
    job = HistorySync.query.one()
    assert job.phase == 'messages'
    real = whatsapp.ingest

    def fail_second(connection, message, **kwargs):
        if message['key']['id'] == 'two':
            raise APIError('Provedor temporariamente indisponível.', 502)
        return real(connection, message, **kwargs)

    monkeypatch.setattr(whatsapp, 'ingest', fail_second)
    checkpoint = deepcopy(job.cursor)
    history.process()
    assert job.status == 'failed' and job.cursor == checkpoint and job.imported == 0
    assert WhatsAppMessage.query.count() == 0
    assert control(client, d, action='resume').status_code == 200
    assert control(client, d, action='cancel').json['sync']['status'] == 'cancelled'
    assert history.process() == 0
    assert control(client, d, action='resume').status_code == 200
    monkeypatch.setattr(whatsapp, 'ingest', real)
    drain()
    assert job.status == 'completed' and job.imported == 2


def test_controls_are_authorized_scoped_idempotent_and_private(env):
    client, d = env
    whatsapp.connection_for(d['ws'].id)
    assert control(client, d, user=d['member']).status_code == 403
    assert client.get('/api/v1/history-sync/whatsapp').status_code == 401
    assert control(client, d, channel='invalid').status_code == 404
    assert control(client, d, action='bad').status_code == 422
    first = control(client, d).json['sync']
    again = control(client, d).json['sync']
    assert first['id'] == again['id'] and HistorySync.query.count() == 1
    assert not {'cursor', 'identity', 'connection_id'} & first.keys()
    outsider = client.get('/api/v1/history-sync/whatsapp', headers=d['headers'](d['outsider']))
    assert outsider.json == {'sync': None}
    assert control(client, d, user=d['outsider'], action='cancel').json == {'sync': None}
    assert HistorySync.query.one().status == 'queued'
    control(client, d, action='cancel')
    connection = whatsapp.connection_for(d['ws'].id)
    connection.instance_name = 'different'
    db.session.commit()
    assert control(client, d, action='resume').status_code == 409
    assert control(client, d).status_code == 200


def test_instagram_pagination_dates_dedup_and_no_side_effects(env, monkeypatch):
    client, d = env
    connection = configure_instagram(client, d)
    monkeypatch.setattr(instagram, 'fetch_profile', Mock(side_effect=AssertionError('No profile requests for history')))
    occurred = (now() - timedelta(days=90)).replace(microsecond=0)

    def message(mid, outgoing=False):
        return {
            'id': mid,
            'created_time': occurred.isoformat(),
            'message': 'Historical',
            'from': {'id': '1234' if outgoing else '5678'},
            'to': {'data': [{'id': '5678' if outgoing else '1234'}]},
        }

    def graph(path, token, **kwargs):
        assert token == 'private-token'
        after = kwargs['params'].get('after')
        if path.endswith('/conversations'):
            if after == 'conversations2':
                return {'data': []}
            return {
                'data': [{'id': 'thread1'}],
                'paging': {
                    'next': 'https://untrusted.invalid/?access_token=secret',
                    'cursors': {'after': 'conversations2'},
                },
            }
        assert path == 'thread1/messages'
        if after == 'messages2':
            return {'data': [message('out', True)]}
        return {'data': [message('in')], 'paging': {'next': 'ignored', 'cursors': {'after': 'messages2'}}}

    monkeypatch.setattr(instagram, 'graph', graph)
    assert control(client, d, channel='instagram').status_code == 200
    drain()
    job = HistorySync.query.one()
    assert job.status == 'completed' and job.imported == 2
    assert InboxMessage.query.count() == 2 and InboxThread.query.one().updated_at == occurred
    assert all(m.created_at == occurred for m in InboxMessage.query.all())
    assert AutomationRun.query.count() == MessageNotification.query.count() == 0
    assert control(client, d, channel='instagram').status_code == 200
    drain()
    assert job.imported == 0 and job.duplicates == 2
    connection.active = False
    db.session.commit()
    assert control(client, d, channel='instagram').status_code == 409


def test_source_change_and_inactive_workspace_stop_worker(env, monkeypatch):
    client, d = env
    whatsapp.connection_for(d['ws'].id)
    control(client, d)
    d['ws'].active = False
    db.session.commit()
    history.process()
    assert HistorySync.query.one().status == 'failed'
    d['ws'].active = True
    db.session.commit()
    control(client, d, action='resume')
    whatsapp.connection_for(d['ws'].id).instance_name = 'changed'
    db.session.commit()
    history.process()
    assert HistorySync.query.one().status == 'failed'


def test_mapping_conflicts_are_quarantined():
    mappings = {}
    for phone in ('5511999990000', '5511988880000', '5511999990000'):
        history.remember_mapping(mappings, {'key': {'remoteJid': '1@lid', 'remoteJidAlt': phone + '@s.whatsapp.net'}})
    assert mappings == {'1@lid': None}


def test_provider_paging_validation():
    with pytest.raises(APIError):
        history.next_cursor({'paging': {'next': 'https://invalid'}})
    with pytest.raises(APIError):
        history.next_cursor({'paging': {'next': 'ignored', 'cursors': {'after': 'same'}}}, 'same')
