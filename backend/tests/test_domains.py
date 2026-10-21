import pytest
import requests
from test_growth import env  # noqa: F401  (shared fixture)

from app.extensions import db
from app.models import CustomDomain, Funnel, now
from app.services import dns_lookup, tls_provider
from app.services import domains as service
from app.services.dns_lookup import DNSLookupError

TARGET = 'antares.douglasgermano.com'


class FakeDNS:
    def __init__(self):
        self.records, self.calls, self.fail = {}, 0, False

    def __call__(self, name, rtype):
        self.calls += 1
        if self.fail:
            raise DNSLookupError('boom')
        return self.records.get((name, rtype), [])


@pytest.fixture()
def dns(monkeypatch):
    fake = FakeDNS()
    monkeypatch.setattr(service, 'dns_query', fake)
    return fake


def add_domain(client, d, host='paginas.cliente.com.br', **extra):
    return client.post('/api/v1/domains', headers=d['headers'](), json={'hostname': host, **extra})


def verified(host, workspace_id, **extra):
    row = CustomDomain(
        workspace_id=workspace_id, hostname=host, verification_token='t' * 32, verified_at=now(), **extra
    )
    db.session.add(row)
    db.session.commit()
    return row


# ---------- validation ----------
@pytest.mark.parametrize(
    'host',
    [
        '',
        'localhost',
        'cliente',
        '192.168.0.1',
        'https://x.com',
        'x.com/path',
        'x.com:8080',
        'a b.com',
        '-x.com',
        'x..com',
        'foo.local',
        'x.internal',
        TARGET,
        'sub.' + TARGET,
        '*.cliente.com',
        'x_y.com',
        'x.123',
    ],
)
def test_invalid_hostnames_are_rejected(env, host):
    client, d = env
    assert add_domain(client, d, host).status_code in (422,), host


def test_hostname_is_normalised_and_idn_encoded(env):
    client, d = env
    assert add_domain(client, d, '  Páginas.Cliente.COM.br. ').json['hostname'] == 'xn--pginas-pta.cliente.com.br'


# ---------- lifecycle ----------
def test_create_returns_dns_instructions_without_leaking_nothing_sensitive(env):
    client, d = env
    body = add_domain(client, d).json
    assert body['status'] == 'pending' and body['url'] == 'https://paginas.cliente.com.br'
    txt = next(r for r in body['dns'] if r['type'] == 'TXT')
    assert txt['name'] == '_antares-verify.paginas.cliente.com.br' and txt['value'].startswith('antares-verify=')
    assert any(r['type'] == 'CNAME' and r['value'] == TARGET for r in body['dns'])
    assert 'verification_token' not in body


def test_duplicates_limits_and_permissions(env):
    client, d = env
    assert add_domain(client, d).status_code == 201
    assert add_domain(client, d, 'PAGINAS.cliente.com.br').status_code == 409
    assert (
        add_domain(
            client,
            d,
            'x.outra.com.br',
        ).status_code
        == 201
    )
    client.application.config['CUSTOM_DOMAINS_PER_WORKSPACE'] = 2
    assert add_domain(client, d, 'y.outra.com.br').status_code == 422
    assert (
        client.post('/api/v1/domains', headers=d['headers'](d['member']), json={'hostname': 'z.com.br'}).status_code
        == 403
    )
    assert client.get('/api/v1/domains', headers=d['headers'](d['member'])).status_code == 200
    # Another account cannot claim a hostname that is already registered.
    assert (
        add_domain(client, {**d, 'headers': lambda: d['headers'](d['outsider'])}, 'paginas.cliente.com.br').status_code
        == 409
    )
    assert client.get('/api/v1/domains', headers=d['headers'](d['outsider'])).json['total'] == 0


def test_verification_moves_through_pending_verified_active(env, dns):
    client, d = env
    created = add_domain(client, d).json
    url = f'/api/v1/domains/{created["id"]}/verify'
    pending = client.post(url, headers=d['headers']()).json
    assert pending['status'] == 'pending' and 'TXT' in pending['last_error']

    token = db.session.get(CustomDomain, created['id']).verification_token
    dns.records[('_antares-verify.paginas.cliente.com.br', 'TXT')] = ['antares-verify=' + token]
    row = db.session.get(CustomDomain, created['id'])
    row.last_checked_at = None
    db.session.commit()
    half = client.post(url, headers=d['headers']()).json
    assert half['status'] == 'verified' and half['verified_at'] and 'CNAME' in half['last_error']

    dns.records[('paginas.cliente.com.br', 'CNAME')] = [TARGET]
    row = db.session.get(CustomDomain, created['id'])
    row.last_checked_at = None
    db.session.commit()
    done = client.post(url, headers=d['headers']()).json
    assert done['status'] == 'active' and done['last_error'] == ''


def test_routing_by_ip_for_apex_domains(env, dns):
    client, d = env
    client.application.config['CUSTOM_DOMAIN_IPS'] = ['203.0.113.10']
    row = verified('cliente.com.br', d['ws'].id)
    dns.records[('cliente.com.br', 'A')] = ['203.0.113.10']
    assert service.verify(row, force=True).routing_ok is True
    assert any(r['type'] == 'A' and r['value'] == '203.0.113.10' for r in service.serialize(row)['dns'])


def test_verification_is_throttled_and_survives_dns_outages(env, dns):
    client, d = env
    created = add_domain(client, d).json
    url = f'/api/v1/domains/{created["id"]}/verify'
    client.post(url, headers=d['headers']())
    calls = dns.calls
    client.post(url, headers=d['headers']())
    assert dns.calls == calls  # second click within the window does not hit the resolver again
    row = db.session.get(CustomDomain, created['id'])
    row.last_checked_at = None
    db.session.commit()
    dns.fail = True
    body = client.post(url, headers=d['headers']()).json
    assert body['status'] == 'pending' and 'DNS' in body['last_error']


def test_domains_are_private_to_their_account_and_deletable(env):
    client, d = env
    created = add_domain(client, d).json
    other = d['headers'](d['outsider'])
    assert client.post(f'/api/v1/domains/{created["id"]}/verify', headers=other).status_code == 404
    assert client.delete(f'/api/v1/domains/{created["id"]}', headers=other).status_code == 404
    assert client.delete(f'/api/v1/domains/{created["id"]}', headers=d['headers']()).status_code == 204
    assert CustomDomain.query.count() == 0


# ---------- public side ----------
def publish_funnel(client, d, headers=None):
    created = client.post(
        '/api/v1/funnels', headers=headers or d['headers'](), json={'name': 'F', 'template': 'blank'}
    ).json
    client.patch(f'/api/v1/funnels/{created["id"]}', headers=headers or d['headers'](), json={'status': 'published'})
    return created


def test_resolve_only_answers_for_verified_domains(env):
    client, d = env
    funnel = publish_funnel(client, d)
    created = add_domain(client, d, funnel_id=funnel['id']).json
    assert client.get('/api/v1/public/domains/resolve?host=paginas.cliente.com.br').status_code == 404
    row = db.session.get(CustomDomain, created['id'])
    row.verified_at = now()
    db.session.commit()
    ok = client.get('/api/v1/public/domains/resolve?host=PAGINAS.cliente.com.br.')
    assert ok.status_code == 200 and ok.json == {'funnel_id': funnel['id']}
    client.patch(f'/api/v1/funnels/{funnel["id"]}', headers=d['headers'](), json={'status': 'draft'})
    assert client.get('/api/v1/public/domains/resolve?host=paginas.cliente.com.br').json == {'funnel_id': None}
    assert client.get('/api/v1/public/domains/resolve').status_code == 404


def test_custom_domain_serves_only_its_own_workspace(env):
    client, d = env
    mine = publish_funnel(client, d)
    theirs = publish_funnel(client, d, d['headers'](d['outsider']))
    verified('paginas.cliente.com.br', d['ws'].id)
    scope = {'X-Custom-Domain': 'paginas.cliente.com.br'}
    assert client.get(f'/api/v1/public/funnels/{mine["id"]}', headers=scope).status_code == 200
    assert client.get(f'/api/v1/public/funnels/{theirs["id"]}', headers=scope).status_code == 404
    assert client.get(f'/api/v1/public/funnels/{theirs["id"]}').status_code == 200  # canonical host is unrestricted
    form = d['form']
    form.active = True
    db.session.commit()
    assert client.get(f'/api/v1/public/forms/{form.id}', headers=scope).status_code == 200
    other_scope = {'X-Custom-Domain': 'outro.cliente.com.br'}
    verified('outro.cliente.com.br', d['other'].id)
    assert client.get(f'/api/v1/public/forms/{form.id}', headers=other_scope).status_code == 404


def test_unknown_or_unverified_hosts_get_nothing(env):
    client, d = env
    funnel = publish_funnel(client, d)
    created = add_domain(client, d).json
    for host in ('naoexiste.com.br', created['hostname']):
        assert (
            client.get(f'/api/v1/public/funnels/{funnel["id"]}', headers={'X-Custom-Domain': host}).status_code == 404
        )


def test_deleting_a_funnel_detaches_its_domains(env):
    client, d = env
    funnel = publish_funnel(client, d)
    created = add_domain(client, d, funnel_id=funnel['id']).json
    assert client.delete(f'/api/v1/funnels/{funnel["id"]}', headers=d['headers']()).status_code == 204
    assert db.session.get(CustomDomain, created['id']).funnel_id is None
    assert Funnel.query.count() == 0


def test_domain_cannot_point_to_another_accounts_funnel(env):
    client, d = env
    theirs = publish_funnel(client, d, d['headers'](d['outsider']))
    assert add_domain(client, d, funnel_id=theirs['id']).status_code == 404
    created = add_domain(client, d).json
    response = client.patch(
        f'/api/v1/domains/{created["id"]}', headers=d['headers'](), json={'funnel_id': theirs['id']}
    )
    assert response.status_code == 404


# ---------- providers ----------
class Reply:
    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body

    def raise_for_status(self):
        pass


def test_dns_lookup_parses_doh_answers(env, monkeypatch):
    client, _ = env
    body = {'Status': 0, 'Answer': [{'type': 16, 'data': '"antares-verify=abc"'}, {'type': 5, 'data': 'x.example.'}]}
    monkeypatch.setattr(requests, 'get', lambda *a, **k: Reply(body))
    with client.application.app_context():
        assert dns_lookup.dns_query('a.com', 'TXT') == ['antares-verify=abc']
        monkeypatch.setattr(requests, 'get', lambda *a, **k: Reply({'Status': 3}))
        assert dns_lookup.dns_query('a.com', 'TXT') == []
        monkeypatch.setattr(requests, 'get', lambda *a, **k: Reply({'Status': 2}))
        with pytest.raises(DNSLookupError):
            dns_lookup.dns_query('a.com', 'TXT')


def test_certificate_lifecycle_with_cloudflare(env, dns, monkeypatch):
    client, d = env
    client.application.config.update(CLOUDFLARE_API_TOKEN='token', CLOUDFLARE_ZONE_ID='zone')
    calls = []
    state = {'status': 'pending', 'ssl': {'status': 'pending_validation'}}

    def fake(method, url, **kwargs):
        calls.append((method, url.rsplit('/custom_hostnames', 1)[1]))
        assert kwargs['headers']['Authorization'] == 'Bearer token'
        if method == 'POST':
            return Reply({'success': True, 'result': {'id': 'ref1', **state}})
        if method == 'GET':
            return Reply({'success': True, 'result': {'id': 'ref1', **state}})
        return Reply({'success': True, 'result': {}})

    monkeypatch.setattr(requests, 'request', fake)
    row = verified('paginas.cliente.com.br', d['ws'].id)
    assert service.verify(row, force=True).tls_status == 'pending' and row.tls_ref == 'ref1'
    assert service.status_of(row) == 'verified'
    state.update(status='active', ssl={'status': 'active'})
    assert service.verify(row, force=True).tls_status == 'active'
    assert row.routing_ok is True and service.status_of(row) == 'active'
    assert client.delete(f'/api/v1/domains/{row.id}', headers=d['headers']()).status_code == 204
    assert calls == [('POST', ''), ('GET', '/ref1'), ('DELETE', '/ref1')]


def test_certificate_errors_are_reported_not_raised(env, dns, monkeypatch):
    client, d = env
    client.application.config.update(CLOUDFLARE_API_TOKEN='token', CLOUDFLARE_ZONE_ID='zone')
    monkeypatch.setattr(
        requests, 'request', lambda *a, **k: Reply({'success': False, 'errors': [{'message': 'quota'}]})
    )
    row = verified('paginas.cliente.com.br', d['ws'].id)
    service.verify(row, force=True)
    assert row.tls_status == 'error' and 'quota' in row.last_error and service.status_of(row) == 'verified'
    assert tls_provider.enabled()
