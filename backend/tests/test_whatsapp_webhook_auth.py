import hashlib
import hmac
import json

from test_growth import env
from app.extensions import db
from app.models import WhatsAppConnection
from app.services.evolution import EvolutionService


def connections(d):
    rows = [
        WhatsAppConnection(workspace_id=d[key].id, instance_name='instance-' + key, webhook_secret='secret-for-' + key)
        for key in ('ws', 'other')
    ]
    db.session.add_all(rows)
    db.session.commit()
    return rows


def test_only_connection_secret_authenticates(env, caplog):
    client, d = env
    a, b = connections(d)
    client.application.config.update(WHATSAPP_WEBHOOK_SECRET='global-secret', EVOLUTION_API_KEY='provider-key')
    body = {'instance': b.instance_name, 'event': 'connection.update', 'data': {'state': 'open'}}
    for secret, apikey in [(a.webhook_secret, None), ('global-secret', None), ('', 'provider-key'), ('', None)]:
        result = client.post(
            '/api/v1/whatsapp/webhook', json={**body, 'apikey': apikey}, headers={'X-Webhook-Secret': secret}
        )
        assert result.status_code == 401
        db.session.refresh(b)
        assert b.last_webhook_at is None and b.state != 'open'
    assert 'whatsapp_webhook_auth_failed' in caplog.text
    assert 'global-secret' not in caplog.text and a.webhook_secret not in caplog.text
    assert (
        client.post('/api/v1/whatsapp/webhook', json=body, headers={'X-Webhook-Secret': b.webhook_secret}).status_code
        == 200
    )
    assert b.state == 'open'


def test_hmac_binds_connection_and_exact_body(env):
    client, d = env
    a, b = connections(d)
    body = json.dumps({'instance': b.instance_name, 'event': 'connection.update', 'data': {'state': 'open'}})
    for key, raw, status in [
        (a.webhook_secret, body, 401),
        (b.webhook_secret, body + ' ', 401),
        (b.webhook_secret, body, 200),
    ]:
        signature = hmac.new(key.encode(), raw.encode(), hashlib.sha256).hexdigest()
        result = client.post(
            '/api/v1/whatsapp/webhook',
            data=body,
            content_type='application/json',
            headers={'X-Webhook-Signature': 'sha256=' + signature},
        )
        assert result.status_code == status


def test_provider_configuration_uses_connection_secret(env, monkeypatch):
    client, d = env
    a, _ = connections(d)
    client.application.config.update(
        EVOLUTION_API_URL='https://provider.example.test',
        EVOLUTION_API_KEY='provider-key',
        WHATSAPP_WEBHOOK_BASE_URL='https://crm.example.test',
    )
    calls = []
    monkeypatch.setattr(EvolutionService, 'request', lambda self, *args, **kwargs: calls.append(args))
    EvolutionService(a).configure_webhook()
    assert calls[0][1] == '/webhook/set/' + a.instance_name
    assert calls[0][2]['webhook']['headers'] == {'X-Webhook-Secret': a.webhook_secret}
