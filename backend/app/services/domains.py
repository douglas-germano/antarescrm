"""Custom domains: validation, ownership proof by DNS, routing check, certificates and public-page scoping."""

import ipaddress
import re
import secrets
from datetime import timedelta

from flask import current_app, request
from sqlalchemy import func

from ..common import APIError, query
from ..extensions import db
from ..models import CustomDomain, Funnel, now
from . import tls_provider
from .dns_lookup import DNSLookupError, dns_query

HEADER = 'X-Custom-Domain'
VERIFY_LABEL = '_antares-verify'
RECHECK_SECONDS = 10
BLOCKED_TLDS = {'local', 'localhost', 'internal', 'test', 'invalid', 'example', 'lan', 'home', 'arpa', 'onion'}
LABEL = re.compile(r'^(?!-)[a-z0-9-]{1,63}(?<!-)$')


def normalize(value):
    """Lower-case ASCII hostname without scheme, path, port or trailing dot; raises APIError when it cannot be a site."""
    raw = (value or '').strip().lower().rstrip('.')
    if not raw or any(ch in raw for ch in '/:@?# _*\\') or raw.startswith('.'):
        raise APIError('Informe apenas o domínio, por exemplo: paginas.suaempresa.com.br.', 422)
    try:
        ipaddress.ip_address(raw)
    except ValueError:
        pass
    else:
        raise APIError('Use um nome de domínio, não um endereço IP.', 422)
    try:
        host = raw.encode('idna').decode('ascii')
    except UnicodeError:
        raise APIError('Domínio inválido.', 422) from None
    labels = host.split('.')
    if len(host) > 253 or len(labels) < 2 or not all(LABEL.match(label) for label in labels):
        raise APIError('Domínio inválido.', 422)
    if labels[-1] in BLOCKED_TLDS or labels[-1].isdigit():
        raise APIError('Este domínio não pode ser usado.', 422)
    app_host = current_app.config['PUBLIC_APP_HOST'].lower()
    if host == app_host or host.endswith('.' + app_host):
        raise APIError('Este domínio pertence à própria plataforma.', 422)
    return host


# ---------- records the customer must create ----------
def txt_value(domain):
    return f'antares-verify={domain.verification_token}'


def dns_records(domain):
    config = current_app.config
    records = [
        {'purpose': 'ownership', 'type': 'TXT', 'name': f'{VERIFY_LABEL}.{domain.hostname}', 'value': txt_value(domain)}
    ]
    records.append(
        {'purpose': 'routing', 'type': 'CNAME', 'name': domain.hostname, 'value': config['CUSTOM_DOMAIN_CNAME_TARGET']}
    )
    for ip in config['CUSTOM_DOMAIN_IPS']:
        records.append({'purpose': 'routing_apex', 'type': 'A', 'name': domain.hostname, 'value': ip})
    return records


def status_of(domain):
    if not domain.verified_at:
        return 'pending'
    tls_ready = domain.tls_status in ('none', 'active')
    return 'active' if domain.routing_ok and tls_ready else 'verified'


def serialize(domain):
    data = domain.to_dict()
    data.pop('verification_token', None)
    data['status'] = status_of(domain)
    data['url'] = 'https://' + domain.hostname
    data['dns'] = dns_records(domain)
    return data


def setup_info():
    config = current_app.config
    return {
        'cname_target': config['CUSTOM_DOMAIN_CNAME_TARGET'],
        'ips': config['CUSTOM_DOMAIN_IPS'],
        'tls_managed': tls_provider.enabled(),
        'limit': config['CUSTOM_DOMAINS_PER_WORKSPACE'],
    }


# ---------- lifecycle ----------
def create(hostname, funnel_id, workspace_id):
    host = normalize(hostname)
    if CustomDomain.query.filter(func.lower(CustomDomain.hostname) == host).first():
        raise APIError('Este domínio já está cadastrado.', 409)
    if query(CustomDomain).count() >= current_app.config['CUSTOM_DOMAINS_PER_WORKSPACE']:
        raise APIError('Limite de domínios desta conta atingido.', 422)
    domain = CustomDomain(
        workspace_id=workspace_id,
        hostname=host,
        funnel_id=str(funnel_id) if funnel_id else None,
        verification_token=secrets.token_hex(16),
    )
    db.session.add(domain)
    db.session.flush()
    return domain


def _fail(domain, message):
    domain.last_error = message[:300]


def verify(domain, force=False):
    """Re-check ownership, routing and certificate; safe to call repeatedly (throttled unless `force`)."""
    if not force and domain.last_checked_at and now() - domain.last_checked_at < timedelta(seconds=RECHECK_SECONDS):
        return domain
    domain.last_checked_at = now()
    domain.last_error = ''
    try:
        if not domain.verified_at:
            found = dns_query(f'{VERIFY_LABEL}.{domain.hostname}', 'TXT')
            if txt_value(domain) in found:
                domain.verified_at = now()
            else:
                _fail(
                    domain, 'Registro TXT de verificação não encontrado. A propagação do DNS pode levar alguns minutos.'
                )
        if domain.verified_at:
            domain.routing_ok = _routing_ok(domain)
            if not domain.routing_ok and not domain.last_error:
                _fail(domain, 'O domínio ainda não aponta para a plataforma. Confira o registro CNAME ou A.')
    except DNSLookupError:
        _fail(domain, 'Não foi possível consultar o DNS agora. Tente novamente em instantes.')
    if domain.verified_at:
        _sync_certificate(domain)
    return domain


def _routing_ok(domain):
    config = current_app.config
    target = config['CUSTOM_DOMAIN_CNAME_TARGET'].lower().rstrip('.')
    if target in dns_query(domain.hostname, 'CNAME'):
        return True
    ips = set(config['CUSTOM_DOMAIN_IPS'])
    return bool(ips and ips & set(dns_query(domain.hostname, 'A')))


def _sync_certificate(domain):
    if not tls_provider.enabled():
        domain.tls_status = 'none'
        return
    try:
        if domain.tls_ref:
            domain.tls_status = tls_provider.refresh(domain.tls_ref)
        else:
            domain.tls_ref, domain.tls_status = tls_provider.register(domain.hostname)
    except tls_provider.TLSProviderError as error:
        domain.tls_status = 'error'
        _fail(domain, str(error))
    # Certificates can be issued over the provider's own routing, so an active certificate also proves routing.
    if domain.tls_status == 'active':
        domain.routing_ok = True


def release(domain):
    """Best-effort removal of the certificate record; the domain row is deleted by the caller."""
    if domain.tls_ref and tls_provider.enabled():
        try:
            tls_provider.remove(domain.tls_ref)
        except tls_provider.TLSProviderError:
            current_app.logger.warning('Não foi possível remover o certificado de %s', domain.hostname)


def detach_funnel(funnel_id):
    CustomDomain.query.filter_by(funnel_id=funnel_id).update({'funnel_id': None})


def set_funnel(domain, funnel_id):
    if funnel_id and not query(Funnel).filter_by(id=str(funnel_id)).first():
        raise APIError('Funil não encontrado.', 404)
    domain.funnel_id = str(funnel_id) if funnel_id else None


# ---------- public side ----------
def find_verified(host):
    host = (host or '').strip().lower().rstrip('.')
    domain = CustomDomain.query.filter_by(hostname=host).first() if host else None
    return domain if domain and domain.verified_at else None


def resolve(host):
    """What the web tier needs to serve `host`: whether it is ours, and which funnel answers on its root path."""
    domain = find_verified(host)
    if not domain:
        raise APIError('Domínio não configurado.', 404)
    funnel = Funnel.query.filter_by(id=domain.funnel_id, workspace_id=domain.workspace_id, status='published').first()
    return {'funnel_id': funnel.id if funnel else None}


def scope_workspace_id():
    """Workspace a public request is limited to: set when it arrives through a customer domain, else None.
    The header is written by the Next.js gateway from the Host it received; the API is not reachable directly."""
    host = request.headers.get(HEADER, '').strip().lower()
    if not host:
        return None
    cache = request.environ.setdefault('antares.public_scope', {})
    if host not in cache:
        domain = find_verified(host)
        cache[host] = domain.workspace_id if domain else False
    if cache[host] is False:
        raise APIError('Página indisponível.', 404)
    return cache[host]


def ensure_scope(workspace_id):
    """A customer domain may only serve content that belongs to its own workspace."""
    scoped = scope_workspace_id()
    if scoped and scoped != workspace_id:
        raise APIError('Página indisponível.', 404)
