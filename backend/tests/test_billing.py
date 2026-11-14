from datetime import timedelta

import pytest
from app import create_app
from app.extensions import db
from app.models import Subscription, User, Workspace, now
from app.services import asaas, billing
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash

TOKEN = 'webhook-token-for-tests'


@pytest.fixture()
def ctx(monkeypatch):
    app = create_app(
        {
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'SQLALCHEMY_ENGINE_OPTIONS': {},
            'JWT_SECRET_KEY': 'test-only-key-with-more-than-thirty-two-characters',
            'RATELIMIT_ENABLED': False,
            'BILLING_ENABLED': True,
            'ASAAS_WEBHOOK_TOKEN': TOKEN,
            'BILLING_PRICE_BRL': '197.00',
        }
    )
    calls = []
    monkeypatch.setattr(asaas, 'create_customer', lambda *a: calls.append(('customer', a)) or {'id': 'cus_1'})
    monkeypatch.setattr(asaas, 'create_subscription', lambda *a: calls.append(('subscription', a)) or {'id': 'sub_1'})
    monkeypatch.setattr(asaas, 'subscription_payments', lambda _id: [{'invoiceUrl': 'https://asaas.test/i/1'}])
    with app.app_context():
        db.create_all()
        ws = Workspace(name='Cliente', slug='cliente')
        db.session.add(ws)
        db.session.flush()
        user = User(
            workspace_id=ws.id,
            name='Ana',
            email='ana@example.invalid',
            role='owner',
            password_hash=generate_password_hash('x'),
        )
        db.session.add(user)
        db.session.commit()
        headers = {'Authorization': 'Bearer ' + create_access_token(identity=user.id, additional_claims={'ver': 0})}
        yield app.test_client(), ws, headers, calls


def set_sub(ws, **fields):
    sub = Subscription.query.filter_by(workspace_id=ws.id).first() or Subscription(workspace_id=ws.id)
    for key, value in fields.items():
        setattr(sub, key, value)
    db.session.add(sub)
    db.session.commit()
    return sub


def webhook(client, event, status='RECEIVED', event_id='evt_1', token=TOKEN):
    return client.post(
        '/api/v1/billing/asaas/webhook',
        json={'id': event_id, 'event': event, 'payment': {'subscription': 'sub_1', 'status': status}},
        headers={'asaas-access-token': token},
    )


def test_workspace_without_subscription_is_never_blocked(ctx):
    client, ws, headers, _ = ctx
    assert client.post('/api/v1/companies', json={'name': 'ACME'}, headers=headers).status_code != 402
    assert client.get('/api/v1/billing', headers=headers).get_json()['access'] == 'full'


def test_expired_trial_is_read_only_but_reads_and_billing_work(ctx):
    client, ws, headers, _ = ctx
    set_sub(ws, status='trialing', trial_ends_at=now() - timedelta(days=1))
    blocked = client.post('/api/v1/companies', json={'name': 'ACME'}, headers=headers)
    assert blocked.status_code == 402 and blocked.get_json()['error']['code'] == 'subscription_required'
    assert client.get('/api/v1/companies', headers=headers).status_code == 200
    assert client.get('/api/v1/billing', headers=headers).get_json()['access'] == 'read_only'


def test_active_trial_allows_writes(ctx):
    client, ws, headers, _ = ctx
    set_sub(ws, status='trialing', trial_ends_at=now() + timedelta(days=3))
    assert client.post('/api/v1/companies', json={'name': 'ACME'}, headers=headers).status_code == 201


def test_past_due_has_grace_then_read_only(ctx):
    _, ws, _, _ = ctx
    sub = set_sub(ws, status='past_due', past_due_since=now() - timedelta(days=2))
    assert billing.access_state(sub) == 'full'
    sub.past_due_since = now() - timedelta(days=6)
    assert billing.access_state(sub) == 'read_only'


def test_agency_client_follows_parent_subscription(ctx):
    _, ws, _, _ = ctx
    child = Workspace(name='Filha', slug='filha', parent_workspace_id=ws.id)
    db.session.add(child)
    db.session.commit()
    set_sub(ws, status='canceled')
    assert billing.workspace_access(child) == 'read_only'


def test_subscribe_creates_customer_and_subscription_due_at_trial_end(ctx):
    client, ws, headers, calls = ctx
    set_sub(ws, status='trialing', trial_ends_at=now() + timedelta(days=10))
    response = client.post('/api/v1/billing/subscribe', json={'cpf_cnpj': '123.456.789-09'}, headers=headers)
    assert response.status_code == 201
    assert response.get_json()['invoice_url'] == 'https://asaas.test/i/1'
    customer_args = dict(calls)['customer']
    assert customer_args[2] == '12345678909'
    due = dict(calls)['subscription'][2]
    assert due == (now() + timedelta(days=10)).date()
    again = client.post('/api/v1/billing/subscribe', json={'cpf_cnpj': '12345678909'}, headers=headers)
    assert again.status_code == 409


def test_subscribe_rejects_invalid_document_and_missing_price(ctx):
    client, ws, headers, _ = ctx
    assert (
        client.post('/api/v1/billing/subscribe', json={'cpf_cnpj': '12345678901234567'}, headers=headers).status_code
        == 422
    )
    ctx[0].application.config['BILLING_PRICE_BRL'] = None
    assert (
        client.post('/api/v1/billing/subscribe', json={'cpf_cnpj': '12345678909'}, headers=headers).status_code == 503
    )


def test_webhook_requires_token(ctx):
    client, ws, _, _ = ctx
    set_sub(ws, asaas_subscription_id='sub_1')
    assert webhook(client, 'PAYMENT_RECEIVED', token='wrong').status_code == 401
    assert client.post('/api/v1/billing/asaas/webhook', json={}).status_code == 401


def test_webhook_payment_activates_and_is_idempotent(ctx):
    client, ws, _, _ = ctx
    set_sub(ws, status='past_due', past_due_since=now(), asaas_subscription_id='sub_1')
    assert webhook(client, 'PAYMENT_RECEIVED').get_json() == {'result': 'applied'}
    sub = Subscription.query.filter_by(workspace_id=ws.id).first()
    assert sub.status == 'active' and sub.past_due_since is None
    set_sub(ws, status='past_due')
    assert webhook(client, 'PAYMENT_RECEIVED').get_json() == {'result': 'duplicate'}
    assert Subscription.query.filter_by(workspace_id=ws.id).first().status == 'past_due'


def test_webhook_overdue_cancel_and_unknown_subscription(ctx):
    client, ws, _, _ = ctx
    set_sub(ws, status='active', asaas_subscription_id='sub_1')
    webhook(client, 'PAYMENT_OVERDUE', status='OVERDUE', event_id='evt_2')
    sub = Subscription.query.filter_by(workspace_id=ws.id).first()
    assert sub.status == 'past_due' and sub.past_due_since is not None
    webhook(client, 'SUBSCRIPTION_DELETED', status='', event_id='evt_3')
    assert Subscription.query.filter_by(workspace_id=ws.id).first().status == 'canceled'
    other = client.post(
        '/api/v1/billing/asaas/webhook',
        json={'id': 'evt_9', 'event': 'PAYMENT_RECEIVED', 'payment': {'subscription': 'sub_zzz'}},
        headers={'asaas-access-token': TOKEN},
    )
    assert other.get_json() == {'result': 'ignored'}


def test_late_overdue_event_does_not_undo_a_paid_invoice(ctx):
    client, ws, _, _ = ctx
    set_sub(ws, status='active', asaas_subscription_id='sub_1')
    webhook(client, 'PAYMENT_OVERDUE', status='RECEIVED', event_id='evt_4')
    assert Subscription.query.filter_by(workspace_id=ws.id).first().status == 'active'


def test_registration_starts_trial_only_when_billing_enabled(ctx):
    client, _, _, _ = ctx
    body = {
        'workspace_name': 'Nova',
        'slug': 'nova',
        'name': 'Beto',
        'email': 'beto@example.invalid',
        'password': 'uma-senha-bem-longa-123',
    }
    assert client.post('/api/v1/auth/register', json=body).status_code == 201
    sub = Subscription.query.join(Workspace).filter(Workspace.slug == 'nova').first()
    assert sub.status == 'trialing' and sub.trial_ends_at > now() + timedelta(days=13)
