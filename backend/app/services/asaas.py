"""Minimal Asaas API client: customers, subscriptions and their payments. Never logs keys or bodies."""

import requests
from flask import current_app

from ..common import APIError

URLS = {'sandbox': 'https://api-sandbox.asaas.com/v3', 'production': 'https://api.asaas.com/v3'}
TIMEOUT = 20


def _call(method, path, *, json=None, params=None):
    key = current_app.config.get('ASAAS_API_KEY')
    if not key:
        raise APIError('Cobrança não configurada.', 503)
    base = URLS.get(current_app.config.get('ASAAS_ENV'), URLS['sandbox'])
    try:
        response = requests.request(
            method,
            base + path,
            json=json,
            params=params,
            headers={'access_token': key, 'User-Agent': 'antares-crm', 'Content-Type': 'application/json'},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        current_app.logger.warning('asaas_unreachable error_type=%s', type(exc).__name__)
        raise APIError('Não foi possível falar com o provedor de cobrança. Tente novamente.', 502) from exc
    if response.status_code >= 400:
        current_app.logger.warning('asaas_error status=%s path=%s', response.status_code, path.split('/')[1])
        message = 'O provedor de cobrança recusou a operação.'
        try:
            errors = response.json().get('errors') or []
            if errors and isinstance(errors[0], dict) and errors[0].get('description'):
                message = str(errors[0]['description'])[:300]
        except ValueError:
            pass
        raise APIError(message, 422 if response.status_code < 500 else 502)
    return response.json()


def create_customer(name, email, cpf_cnpj, workspace_id):
    return _call(
        'POST',
        '/customers',
        json={'name': name, 'email': email, 'cpfCnpj': cpf_cnpj, 'externalReference': workspace_id},
    )


def create_subscription(customer_id, value, next_due_date, workspace_id, description):
    return _call(
        'POST',
        '/subscriptions',
        json={
            'customer': customer_id,
            'billingType': 'UNDEFINED',  # the customer picks Pix, boleto or card on the hosted invoice
            'value': value,
            'nextDueDate': next_due_date.isoformat(),
            'cycle': 'MONTHLY',
            'description': description,
            'externalReference': workspace_id,
        },
    )


def subscription_payments(subscription_id):
    return _call('GET', f'/subscriptions/{subscription_id}/payments', params={'limit': 1}).get('data') or []


def cancel_subscription(subscription_id):
    return _call('DELETE', f'/subscriptions/{subscription_id}')
