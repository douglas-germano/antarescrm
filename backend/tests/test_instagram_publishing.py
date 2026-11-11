import io
from datetime import timedelta
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from app.common import APIError
from app.extensions import db
from app.models import (
    Contact,
    InboxThread,
    InstagramConnection,
    InstagramInsightSnapshot,
    InstagramMedia,
    InstagramPost,
    now,
)
from app.services import instagram as service
from app.services.instagram import client as instagram_client
from app.services.instagram import insights, publishing
from helpers.instagram import configure_instagram, event, receive

JPEG = b'\xff\xd8\xff\xe0' + b'0' * 64
FULL = ','.join(
    (
        'instagram_business_basic',
        'instagram_business_manage_messages',
        'instagram_business_content_publish',
        'instagram_business_manage_insights',
    )
)


def second_account(d, instagram_id='4321', username='cliente.dois', workspace=None):
    row = InstagramConnection(
        workspace_id=(workspace or d['ws']).id,
        instagram_id=instagram_id,
        username=username,
        encrypted_token=service.cipher().encrypt(b'second-token').decode(),
        scopes=FULL,
    )
    db.session.add(row)
    db.session.commit()
    return row


def publishable(client, d, tmp_path):
    client.application.config['PROJECT_FILES_DIR'] = str(tmp_path)
    row = configure_instagram(client, d)
    row.scopes = FULL
    db.session.commit()
    return row


def upload(client, d, content=JPEG, name='foto.jpg', user=None):
    return client.post(
        '/api/v1/instagram/media',
        headers=d['headers'](user) if user else d['headers'](),
        data={'file': (io.BytesIO(content), name)},
        content_type='multipart/form-data',
    )


class FakeGraph:
    """Records Graph calls and answers like Instagram's publishing endpoints."""

    def __init__(self, statuses=None, publish=None):
        self.calls, self.statuses, self.publish, self.next = [], statuses or {}, publish, 100

    def __call__(self, path, token, method='GET', detail=False, **kwargs):
        params = kwargs.get('params') or {}
        self.calls.append((method, path, params))
        if path.endswith('/media') and method == 'POST':
            self.next += 1
            return {'id': str(self.next)}
        if path.endswith('/media_publish'):
            if self.publish:
                raise self.publish
            return {'id': '9000'}
        if path == '9000':
            return {'permalink': 'https://www.instagram.com/p/abc/'}
        return {'status_code': self.statuses.get(path, 'FINISHED')}


# ---------- several accounts ----------
def test_workspace_holds_several_accounts_and_one_profile_stays_in_one_workspace(env, monkeypatch):
    client, d = env
    configure_instagram(client, d)
    monkeypatch.setattr(instagram_client, 'profile', lambda token: {'user_id': '4321', 'username': 'cliente.dois'})
    service.connect(d['ws'].id, 'second-token', 5000, FULL)
    db.session.commit()
    listing = client.get('/api/v1/instagram/connection', headers=d['headers']()).json
    assert [item['username'] for item in listing['connections']] == ['testprofile', 'cliente.dois']
    assert listing['connected'] and listing['connection']['username'] == 'testprofile'
    assert listing['connections'][1]['can_publish'] and not listing['connections'][0]['can_publish']
    team = client.get('/api/v1/instagram/accounts', headers=d['headers'](d['member'])).json['items']
    assert len(team) == 2 and 'scopes' not in team[0] and 'encrypted_token' not in str(team)
    with pytest.raises(APIError) as error:
        service.connect(d['other'].id, 'stolen')
    assert error.value.status == 409
    second = InstagramConnection.query.filter_by(instagram_id='4321').one()
    assert (
        client.post(
            '/api/v1/instagram/disconnect', headers=d['headers'](), json={'connection_id': second.id}
        ).status_code
        == 200
    )
    assert not db.session.get(InstagramConnection, second.id).active
    assert InstagramConnection.query.filter_by(instagram_id='1234').one().active


def test_replies_and_automations_answer_through_the_account_that_received_the_conversation(env, monkeypatch):
    client, d = env
    configure_instagram(client, d)
    second_account(d)
    body = event()
    body['entry'][0]['id'] = '4321'
    body['entry'][0]['messaging'][0]['recipient']['id'] = '4321'
    assert receive(client, body).status_code == 200
    thread = InboxThread.query.one()
    assert thread.address == '4321:5678'
    inbox = client.get('/api/v1/inbox', headers=d['headers']()).json['items']
    assert inbox[0]['instagram_account'] == 'cliente.dois'
    calls = []

    def send(path, token, method='GET', **kwargs):
        calls.append((path, token))
        return {'message_id': 'out-' + str(len(calls))}

    monkeypatch.setattr(instagram_client, 'graph', send)
    response = client.post(
        f'/api/v1/inbox/inbox/{thread.id}/messages',
        headers=d['headers'](),
        json={'content': 'Oi', 'idempotency_key': str(uuid4())},
    )
    assert response.status_code == 200 and response.json['status'] == 'sent'
    contact = Contact.query.one()
    assert service.automation_message(contact, 'Olá', d['ws'], 'auto-1')
    assert calls == [('4321/messages', 'second-token'), ('4321/messages', 'second-token')]
    second = InstagramConnection.query.filter_by(instagram_id='4321').one()
    second.active = False
    db.session.commit()
    response = client.post(
        f'/api/v1/inbox/inbox/{thread.id}/messages',
        headers=d['headers'](),
        json={'content': 'Oi de novo', 'idempotency_key': str(uuid4())},
    )
    assert response.status_code == 409


def test_oauth_requests_publishing_and_metrics_and_records_granted_permissions(env, monkeypatch):
    client, d = env
    configure_instagram(client, d)
    url = client.post('/api/v1/instagram/connect', headers=d['headers'](), json={}).json['url']
    query = parse_qs(urlparse(url).query)
    assert 'instagram_business_content_publish' in query['scope'][0]
    assert 'instagram_business_manage_insights' in query['scope'][0]
    monkeypatch.setattr(
        service,
        'oauth_tokens',
        lambda code: {'access_token': 'new', 'expires_in': 5000, 'permissions': 'instagram_business_basic'},
    )
    monkeypatch.setattr(instagram_client, 'profile', lambda token: {'user_id': '7777', 'username': 'novo'})
    monkeypatch.setattr(instagram_client, 'graph', lambda *args, **kwargs: {'success': True})
    response = client.post(
        '/api/v1/instagram/complete', headers=d['headers'](), json={'state': query['state'][0], 'code': 'c'}
    )
    assert response.status_code == 200 and response.json['username'] == 'novo'
    assert not response.json['can_publish'] and InstagramConnection.query.count() == 2


# ---------- media ----------
def test_uploads_accept_jpeg_and_video_and_public_link_opens_only_for_pending_posts(env, tmp_path):
    client, d = env
    publishable(client, d, tmp_path)
    assert upload(client, d, b'\x89PNG' + b'0' * 20, 'foto.png').status_code == 422
    assert upload(client, d, b'not-a-jpeg', 'foto.jpg').status_code == 422
    media = upload(client, d).json
    assert media['kind'] == 'image' and 'public_token' not in media and 'storage_key' not in media
    row = db.session.get(InstagramMedia, media['id'])
    public = '/api/v1/public/instagram-media/' + row.public_token
    assert client.get(public).status_code == 404
    assert client.get(f'/api/v1/instagram/media/{row.id}/file', headers=d['headers']()).data == JPEG
    assert client.get(f'/api/v1/instagram/media/{row.id}/file', headers=d['headers'](d['outsider'])).status_code == 404
    post = client.post(
        '/api/v1/instagram/posts',
        headers=d['headers'](),
        json={'media_type': 'IMAGE', 'caption': 'Oi', 'items': [{'media_id': row.id}], 'action': 'publish'},
    )
    assert post.status_code == 201 and post.json['status'] == 'scheduled'
    response = client.get(public)
    assert response.status_code == 200 and response.data == JPEG and response.mimetype == 'image/jpeg'
    assert client.delete(f'/api/v1/instagram/media/{row.id}', headers=d['headers']()).status_code == 409


# ---------- posts ----------
def test_post_validation_permissions_and_drafts(env, tmp_path):
    client, d = env
    connection = publishable(client, d, tmp_path)
    media = upload(client, d).json['id']
    path = '/api/v1/instagram/posts'
    base = {'connection_id': connection.id, 'media_type': 'IMAGE', 'items': [{'media_id': media}]}
    assert client.post(path, headers=d['headers'](), json={**base, 'media_type': 'STORY'}).status_code == 422
    assert client.post(path, headers=d['headers'](), json={**base, 'caption': '#a ' * 31}).status_code == 422
    assert client.post(path, headers=d['headers'](), json={**base, 'caption': 'x' * 2201}).status_code == 422
    assert client.post(path, headers=d['headers'](), json={**base, 'media_type': 'CAROUSEL'}).status_code == 422
    assert client.post(path, headers=d['headers'](), json={**base, 'media_type': 'REELS'}).status_code == 422
    link = {**base, 'items': [{'url': 'http://example.com/a.jpg', 'kind': 'image'}]}
    assert client.post(path, headers=d['headers'](), json=link).status_code == 422
    assert client.post(path, headers=d['headers'](d['outsider']), json=base).status_code in (404, 409)
    draft = client.post(path, headers=d['headers'](d['member']), json={**base, 'caption': 'Rascunho'})
    assert draft.status_code == 201 and draft.json['status'] == 'draft'
    member_schedule = client.post(f'{path}/{draft.json["id"]}/schedule', headers=d['headers'](d['member']), json={})
    assert member_schedule.status_code == 403
    past = (now() - timedelta(days=1)).isoformat()
    assert (
        client.post(
            f'{path}/{draft.json["id"]}/schedule', headers=d['headers'](), json={'scheduled_at': past}
        ).status_code
        == 422
    )
    later = (now() + timedelta(days=2)).isoformat()
    scheduled = client.post(f'{path}/{draft.json["id"]}/schedule', headers=d['headers'](), json={'scheduled_at': later})
    assert scheduled.json['status'] == 'scheduled'
    assert publishing.process() == 0  # Not due yet.
    cancel = client.post(f'{path}/{draft.json["id"]}/cancel', headers=d['headers'](), json={})
    assert cancel.json['status'] == 'draft'
    edited = client.patch(f'{path}/{draft.json["id"]}', headers=d['headers'](), json={'caption': 'Nova legenda'})
    assert edited.json['caption'] == 'Nova legenda'
    assert client.get(path, headers=d['headers'](d['outsider'])).json['items'] == []
    connection.scopes = None  # Authorized before publishing was requested.
    db.session.commit()
    assert client.post(path, headers=d['headers'](), json=base).status_code == 409


def test_worker_publishes_an_image_once_with_its_public_link(env, tmp_path, monkeypatch):
    client, d = env
    publishable(client, d, tmp_path)
    media = upload(client, d).json['id']
    created = client.post(
        '/api/v1/instagram/posts',
        headers=d['headers'](),
        json={'media_type': 'IMAGE', 'caption': 'Lançamento', 'items': [{'media_id': media}], 'action': 'publish'},
    ).json
    graph = FakeGraph()
    monkeypatch.setattr(instagram_client, 'graph', graph)
    assert publishing.process() == 1
    post = db.session.get(InstagramPost, created['id'])
    assert post.status == 'published' and post.ig_media_id == '9000'
    assert post.permalink == 'https://www.instagram.com/p/abc/'
    container = graph.calls[0]
    token = db.session.get(InstagramMedia, media).public_token
    assert container[1] == '1234/media' and container[2]['image_url'].endswith('/api/public/media/' + token)
    assert container[2]['caption'] == 'Lançamento'
    assert [c for c in graph.calls if c[1].endswith('media_publish')] == [
        ('POST', '1234/media_publish', {'creation_id': '101'})
    ]
    assert publishing.process() == 0
    assert client.get('/api/v1/public/instagram-media/' + token).status_code == 404  # Closed after publishing.
    assert client.delete(f'/api/v1/instagram/posts/{post.id}', headers=d['headers']()).status_code == 200


def test_worker_waits_for_video_and_builds_carousels(env, tmp_path, monkeypatch):
    client, d = env
    connection = publishable(client, d, tmp_path)
    reel = InstagramPost(
        workspace_id=d['ws'].id,
        connection_id=connection.id,
        media_type='REELS',
        caption='Reel',
        items=[{'url': 'https://cdn.example.com/v.mp4', 'kind': 'video'}],
        status='scheduled',
        scheduled_at=now() - timedelta(seconds=2),
        containers={},
    )
    carousel = InstagramPost(
        workspace_id=d['ws'].id,
        connection_id=connection.id,
        media_type='CAROUSEL',
        caption='Carrossel',
        items=[
            {'url': 'https://cdn.example.com/a.jpg', 'kind': 'image'},
            {'url': 'https://cdn.example.com/b.mp4', 'kind': 'video'},
        ],
        status='scheduled',
        scheduled_at=now() - timedelta(seconds=1),
        containers={},
    )
    db.session.add_all([reel, carousel])
    db.session.commit()
    graph = FakeGraph(statuses={'101': 'IN_PROGRESS'})
    monkeypatch.setattr(instagram_client, 'graph', graph)
    publishing.process()
    reel, carousel = db.session.get(InstagramPost, reel.id), db.session.get(InstagramPost, carousel.id)
    assert reel.status == 'processing' and reel.containers == {'parent': '101'}
    reel_params = graph.calls[0][2]
    assert reel_params['media_type'] == 'REELS' and reel_params['video_url'].endswith('v.mp4')
    graph.statuses = {}
    for _ in range(3):
        publishing.process()
    reel, carousel = db.session.get(InstagramPost, reel.id), db.session.get(InstagramPost, carousel.id)
    assert reel.status == carousel.status == 'published'
    children = [c for c in graph.calls if c[2].get('is_carousel_item')]
    assert len(children) == 2 and children[1][2]['media_type'] == 'VIDEO'
    parent = next(c for c in graph.calls if c[2].get('media_type') == 'CAROUSEL')
    assert parent[2]['children'] == '102,103' and parent[2]['caption'] == 'Carrossel'


def test_refusals_fail_ambiguous_publishes_become_unknown_and_never_repeat(env, tmp_path, monkeypatch):
    client, d = env
    connection = publishable(client, d, tmp_path)

    def post():
        row = InstagramPost(
            workspace_id=d['ws'].id,
            connection_id=connection.id,
            media_type='IMAGE',
            items=[{'url': 'https://cdn.example.com/a.jpg', 'kind': 'image'}],
            status='scheduled',
            scheduled_at=now(),
            containers={},
        )
        db.session.add(row)
        db.session.commit()
        return row.id

    refused = post()
    monkeypatch.setattr(
        instagram_client,
        'graph',
        FakeGraph(publish=instagram_client.GraphError('O Instagram recusou: proporção', 502, 36003, 'proporção')),
    )
    publishing.process()
    assert db.session.get(InstagramPost, refused).status == 'failed'
    ambiguous = post()
    graph = FakeGraph(publish=TimeoutError('network'))
    monkeypatch.setattr(instagram_client, 'graph', graph)
    publishing.process()
    publishing.process()
    row = db.session.get(InstagramPost, ambiguous)
    assert row.status == 'unknown' and 'Confira no Instagram' in row.error
    assert len([c for c in graph.calls if c[1].endswith('media_publish')]) == 1
    stale = post()
    row = db.session.get(InstagramPost, stale)
    row.status = 'publishing'
    db.session.commit()
    InstagramPost.query.filter_by(id=stale).update({'updated_at': now() - timedelta(minutes=11)})
    db.session.commit()
    publishing.process()
    assert db.session.get(InstagramPost, stale).status == 'unknown'
    retry = client.post(f'/api/v1/instagram/posts/{refused}/schedule', headers=d['headers'](), json={})
    assert retry.status_code == 200 and retry.json['status'] == 'scheduled'
    connection.active = False
    db.session.commit()
    publishing.process()
    assert 'desconectado' in db.session.get(InstagramPost, refused).error


# ---------- metrics ----------
def insights_graph(calls, fail_metric=None):
    def graph(path, token, method='GET', detail=False, **kwargs):
        params = kwargs.get('params') or {}
        calls.append((path, params))
        if path == '1234':
            return {'username': 'testprofile', 'followers_count': 1500, 'media_count': 40}
        metric = params.get('metric', '')
        if fail_metric and fail_metric in metric.split(','):
            raise instagram_client.GraphError('recusado', 502, 100, 'invalid metric')
        if path == '1234/insights' and params.get('metric_type') == 'total_value' and 'breakdown' not in params:
            return {'data': [{'name': name, 'total_value': {'value': 10}} for name in metric.split(',')]}
        if path == '1234/insights' and params.get('breakdown'):
            raise instagram_client.GraphError('poucos seguidores', 502, 10, 'not enough followers')
        if path == '1234/insights':
            return {'data': [{'name': metric, 'values': [{'value': 5, 'end_time': '2026-11-10T08:00:00+0000'}]}]}
        if path == '1234/media':
            return {'data': [{'id': '555', 'caption': 'Post', 'media_type': 'IMAGE', 'like_count': 3}]}
        if path == '555/insights':
            return {'data': [{'name': 'reach', 'values': [{'value': 80}]}]}
        raise AssertionError(path)

    return graph


def test_metrics_are_partial_cached_and_kept_as_history(env, monkeypatch):
    client, d = env
    connection = configure_instagram(client, d)
    path = f'/api/v1/instagram/accounts/{connection.id}/insights'
    assert client.get(path, headers=d['headers']()).status_code == 409  # Legacy authorization.
    connection.scopes = FULL
    db.session.commit()
    calls = []
    monkeypatch.setattr(instagram_client, 'graph', insights_graph(calls, fail_metric='replies'))
    data = client.get(path, headers=d['headers'](d['member'])).json
    assert data['account']['followers_count'] == 1500
    assert data['totals']['reach'] == 10 and 'replies' not in data['totals']  # Retried one by one.
    assert data['series']['reach'][0] == {'date': '2026-11-10', 'value': 5}
    assert data['media'][0]['insights'] == {'reach': 80}
    reasons = {(e['part'], e['reason']) for e in data['errors']}
    assert ('metric:replies', 'unavailable') in reasons and ('audience:age', 'permission') in reasons
    assert data['history'] == [{'date': data['history'][0]['date'], 'followers': 1500}]
    count = len(calls)
    assert (
        client.get(path, headers=d['headers']()).status_code == 200 and len(calls) == count
    )  # Served from the snapshot.
    assert (
        client.get(path + '?refresh=1', headers=d['headers']()).status_code == 200 and len(calls) == count
    )  # 5-minute floor.
    InstagramInsightSnapshot.query.update({'updated_at': now() - timedelta(minutes=10)})
    db.session.commit()
    assert client.get(path + '?refresh=1', headers=d['headers']()).status_code == 200 and len(calls) > count
    assert client.get(path + '?days=9', headers=d['headers']()).status_code == 422
    assert client.get(path, headers=d['headers'](d['outsider'])).status_code == 404


def test_worker_takes_one_daily_snapshot_per_account(env, monkeypatch):
    client, d = env
    connection = configure_instagram(client, d)
    connection.scopes = FULL
    db.session.commit()
    calls = []
    monkeypatch.setattr(instagram_client, 'graph', insights_graph(calls))
    insights._attempted.clear()
    assert insights.process() == 1
    assert insights.process() == 0
    assert InstagramInsightSnapshot.query.count() == 1
