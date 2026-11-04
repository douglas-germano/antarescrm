"""Real PostgreSQL worker claims; all provider I/O is replaced by bounded test adapters."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from app.extensions import db
from app.models import AutomationJob, AutomationRule, Contact, InboxMessage, Task
from app.services.automations import emit, process
from app.services.communications import dispatch, enqueue

pytestmark = pytest.mark.skipif(
    not os.environ.get('ANTARES_POSTGRES_TEST_URL'), reason='Disposable PostgreSQL database required'
)


def test_two_workers_do_not_skip_locked_predecessor(pg, monkeypatch):
    app, workspace_id, _, _ = pg
    rule = AutomationRule(
        workspace_id=workspace_id,
        name='Sequential',
        event='contact.created',
        active=True,
        task_title='Legacy',
        actions=[{'kind': 'create_task', 'title': 'First'}, {'kind': 'create_task', 'title': 'Second'}],
    )
    contact = Contact(workspace_id=workspace_id, name='Worker contact')
    db.session.add_all([rule, contact])
    db.session.flush()
    emit(workspace_id, 'contact.created', contact.id, contact)
    db.session.commit()
    import app.services.automations as service

    original = service.execute
    entered = Event()
    release = Event()

    def controlled(job, *args):
        if job.position == 0:
            entered.set()
            assert release.wait(timeout=10)
        return original(job, *args)

    monkeypatch.setattr(service, 'execute', controlled)

    def work():
        with app.app_context():
            return process(workspace_id, limit=1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(work)
        try:
            assert entered.wait(timeout=10)
            assert pool.submit(work).result(timeout=10) == []
        finally:
            release.set()
        assert len(first.result(timeout=10)) == 1
    assert len(process(workspace_id)) == 1
    db.session.expire_all()
    assert {row.status for row in AutomationJob.query.filter_by(workspace_id=workspace_id)} == {'completed'}
    assert Task.query.filter_by(workspace_id=workspace_id).count() == 2


def test_concurrent_dispatch_claims_one_message_once(pg, monkeypatch):
    app, workspace_id, _, user_id = pg
    app.config['COMMUNICATION_ACCOUNTS'] = {
        workspace_id: {'email': {'host': 'smtp.example.test', 'from_address': 'sender@example.test'}}
    }
    contact = Contact(workspace_id=workspace_id, name='Recipient', email='recipient@example.test')
    db.session.add(contact)
    db.session.flush()
    enqueue(workspace_id, contact, 'email', 'Hello', 'Test', str(uuid4()), user_id)
    db.session.commit()
    entered = Event()
    release = Event()
    calls = []

    def deliver(thread, message):
        calls.append(message.id)
        entered.set()
        assert release.wait(timeout=10)
        return 'provider-id'

    monkeypatch.setattr('app.services.communications.deliver', deliver)

    def work():
        with app.app_context():
            return dispatch(workspace_id, limit=1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(work)
        try:
            assert entered.wait(timeout=10)
            assert pool.submit(work).result(timeout=10) == []
        finally:
            release.set()
        assert len(first.result(timeout=10)) == 1
    assert len(calls) == 1
    db.session.expire_all()
    assert InboxMessage.query.filter_by(workspace_id=workspace_id).one().status == 'sent'


def test_paginated_deals_keep_summary_with_attention_and_stale_sort(pg):
    from datetime import timedelta

    from app.models import Opportunity, PipelineStage, now
    from flask_jwt_extended import create_access_token

    app, workspace_id, _, user_id = pg
    contact = Contact(workspace_id=workspace_id, name='João da Silva', phone='+5566996499089', source='Site')
    db.session.add(contact)
    stage = PipelineStage.query.filter_by(workspace_id=workspace_id).first()
    stage.probability = 50
    db.session.flush()
    for index in range(3):
        db.session.add(
            Opportunity(
                workspace_id=workspace_id,
                contact_id=contact.id,
                stage_id=stage.id,
                title=f'Negócio {index}',
                amount=100,
                created_at=now() - timedelta(days=index),
            )
        )
    db.session.commit()
    token = create_access_token(identity=user_id, additional_claims={'ver': 0, 'wid': workspace_id})
    with app.test_client() as client:
        result = client.get(
            '/api/v1/opportunities?status=open&attention=true&sort=stale&direction=desc&search=joao+silva&per_page=1&page=2',
            headers={'Authorization': 'Bearer ' + token},
        )
        assert result.status_code == 200
        assert result.json['total'] == 3 and result.json['items'][0]['title'] == 'Negócio 1'
        assert result.json['summary']['weighted'] == '150.00'


def test_concurrent_instagram_echo_is_recorded_once_without_a_lead(pg):
    import hashlib
    import hmac
    import json
    from threading import Barrier

    from app.models import InboxThread, InstagramConnection, InstagramEvent, now
    from cryptography.fernet import Fernet

    app, workspace_id, _, _ = pg
    app.config.update(INSTAGRAM_APP_SECRET='echo-test-secret', INSTAGRAM_ENCRYPTION_KEY=Fernet.generate_key().decode())
    connection = InstagramConnection(
        workspace_id=workspace_id, instagram_id='12345678', username='fixture', encrypted_token='unused'
    )
    db.session.add(connection)
    db.session.commit()
    body = json.dumps(
        {
            'object': 'instagram',
            'entry': [
                {
                    'id': '12345678',
                    'messaging': [
                        {
                            'sender': {'id': '12345678'},
                            'recipient': {'id': '87654321'},
                            'timestamp': int(now().timestamp() * 1000),
                            'message': {'mid': 'concurrent-echo', 'text': 'Native app send', 'is_echo': True},
                        }
                    ],
                }
            ],
        }
    ).encode()
    signature = 'sha256=' + hmac.new(b'echo-test-secret', body, hashlib.sha256).hexdigest()
    barrier = Barrier(2)

    def post():
        with app.test_client() as client:
            barrier.wait(timeout=10)
            return client.post(
                '/api/v1/instagram/webhook',
                data=body,
                content_type='application/json',
                headers={'X-Hub-Signature-256': signature},
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: post(), range(2))) == [200, 200]
    db.session.expire_all()
    assert InstagramEvent.query.filter_by(workspace_id=workspace_id).count() == 1
    assert InboxThread.query.filter_by(workspace_id=workspace_id).count() == 1
    assert InboxMessage.query.filter_by(workspace_id=workspace_id).one().direction == 'out'
    assert Contact.query.filter_by(workspace_id=workspace_id).count() == 0


def test_access_token_can_be_consumed_only_once_concurrently(pg):
    import hashlib
    from datetime import timedelta
    from threading import Barrier

    from app.models import User, UserAccessToken, now

    app, workspace_id, _, user_id = pg
    user = db.session.get(User, user_id)
    token = 'single-use-postgres-fixture-token-with-enough-entropy'
    db.session.add(
        UserAccessToken(
            workspace_id=workspace_id,
            user_id=user_id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            purpose='reset',
            token_version=user.token_version,
            email=user.email,
            expires_at=now() + timedelta(minutes=30),
        )
    )
    db.session.commit()
    barrier = Barrier(2)

    def accept():
        with app.test_client() as client:
            barrier.wait(timeout=10)
            return client.post(
                '/api/v1/auth/accept-access', json={'token': token, 'password': 'postgres-new-password'}
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: accept(), range(2))) == [200, 422]
    db.session.expire_all()
    assert db.session.get(User, user_id).token_version == 1


def test_campaign_send_claim_is_not_repeated_by_concurrent_requests(pg, monkeypatch):
    from app.models import BrevoConnection, CampaignRecipient, EmailCampaign, now
    from app.services import brevo, campaigns
    from flask_jwt_extended import create_access_token

    app, workspace_id, _, user_id = pg
    connection = BrevoConnection(
        workspace_id=workspace_id,
        sender_email='sender@example.test',
        sender_name='Fixture',
        encrypted_key=brevo.cipher().encrypt(b'fixture-key').decode(),
        webhook_secret='fixture-secret',
        validated_at=now(),
        webhook_id=51,
    )
    person = Contact(workspace_id=workspace_id, name='Fixture', email='recipient@example.test', tags=['Newsletter'])
    db.session.add_all([connection, person])
    db.session.flush()
    row = EmailCampaign(
        workspace_id=workspace_id,
        name='Fixture',
        subject='Fixture',
        content='Fixture',
        audience={'tag': 'Newsletter'},
        status='ready',
        connection_id=connection.id,
        connection_version=connection.version,
        provider_id=44,
        audience_hash=campaigns.fingerprint([{'email': person.email}]),
        recipient_count=1,
    )
    db.session.add(row)
    db.session.flush()
    db.session.add(
        CampaignRecipient(workspace_id=workspace_id, campaign_id=row.id, contact_id=person.id, email=person.email)
    )
    db.session.commit()
    path = f'/api/v1/campaigns/{row.id}/send'
    body = {'consent_confirmed': True, 'audience_hash': row.audience_hash}
    token = create_access_token(identity=user_id, additional_claims={'ver': 0, 'wid': workspace_id})
    entered, release, calls = Event(), Event(), []

    def api(key, route, method='GET', **kwargs):
        calls.append(route)
        entered.set()
        assert release.wait(timeout=10)
        return {}

    monkeypatch.setattr(brevo, 'api', api)

    def send():
        with app.test_client() as client:
            return client.post(path, json=body, headers={'Authorization': 'Bearer ' + token}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(send)
        try:
            assert entered.wait(timeout=10)
            assert pool.submit(send).result(timeout=10) == 200
        finally:
            release.set()
        assert first.result(timeout=10) == 200
    assert calls == ['emailCampaigns/44/sendNow']
    with app.test_client() as client:
        result = client.get(
            '/api/v1/contacts?has_email=true&tag=Newsletter', headers={'Authorization': 'Bearer ' + token}
        )
        assert result.status_code == 200 and result.json['total'] == 1
