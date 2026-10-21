"""Certificates for customer hostnames. Only Cloudflare for SaaS (custom hostnames) is supported; without its
credentials the platform assumes TLS is terminated elsewhere (for example a proxy that issues certificates on demand)."""

import requests
from flask import current_app

API = 'https://api.cloudflare.com/client/v4'


class TLSProviderError(Exception):
    pass


def enabled():
    return bool(current_app.config.get('CLOUDFLARE_API_TOKEN') and current_app.config.get('CLOUDFLARE_ZONE_ID'))


def _call(method, path='', **kwargs):
    config = current_app.config
    url = f'{API}/zones/{config["CLOUDFLARE_ZONE_ID"]}/custom_hostnames{path}'
    try:
        response = requests.request(
            method, url, headers={'Authorization': 'Bearer ' + config['CLOUDFLARE_API_TOKEN']}, timeout=10, **kwargs
        )
        body = response.json()
    except (requests.RequestException, ValueError):
        raise TLSProviderError('Não foi possível falar com o provedor de certificados.') from None
    if not body.get('success'):
        errors = body.get('errors') or [{}]
        raise TLSProviderError(str(errors[0].get('message') or 'O provedor de certificados recusou o pedido.')[:200])
    return body.get('result') or {}


def state(result):
    """Collapse the provider's two statuses (hostname and certificate) into none/pending/active/error."""
    status, ssl = result.get('status'), (result.get('ssl') or {}).get('status')
    if status == 'active' and ssl == 'active':
        return 'active'
    if status in ('blocked', 'deleted', 'moved') or ssl in ('deleted', 'expired'):
        return 'error'
    return 'pending'


def register(hostname):
    result = _call(
        'POST',
        json={'hostname': hostname, 'ssl': {'method': 'http', 'type': 'dv', 'settings': {'min_tls_version': '1.2'}}},
    )
    return result['id'], state(result)


def refresh(ref):
    return state(_call('GET', '/' + ref))


def remove(ref):
    _call('DELETE', '/' + ref)
