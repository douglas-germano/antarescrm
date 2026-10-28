"""Brevo API transport. Credentials and provider response bodies never reach API clients."""

import base64
import hashlib
import secrets

import requests
from cryptography.fernet import Fernet
from flask import current_app

from ..common import APIError
from ..extensions import db
from ..models import BrevoConnection, EmailCampaign, now


def cipher():
    key = current_app.config.get('BREVO_ENCRYPTION_KEY')
    if not key:
        key = base64.urlsafe_b64encode(
            hashlib.sha256(('antares-brevo:' + current_app.config['SECRET_KEY']).encode()).digest()
        )
    return Fernet(key)


def api(key, path, method='GET', **kwargs):
    try:
        response = requests.request(
            method,
            'https://api.brevo.com/v3/' + path,
            headers={'api-key': key, 'Accept': 'application/json'},
            timeout=(3, 8),
            **kwargs,
        )
    except requests.Timeout:
        raise APIError(
            'O Brevo demorou a responder. Consulte o provedor antes de repetir uma operação de envio.',
            503,
            code='brevo_timeout',
        ) from None
    except requests.RequestException:
        raise APIError(
            'Não foi possível acessar o Brevo. Consulte o provedor antes de repetir uma operação de envio.',
            503,
            code='brevo_unavailable',
        ) from None
    if not response.ok:
        # Classify known provider errors; never log or expose its arbitrary message, key or response body.
        try:
            body = response.json()
        except ValueError:
            body = {}
        message = str(body.get('message', '')).lower() if isinstance(body, dict) else ''
        ip_blocked = any(
            term in message
            for term in (
                'unrecognised ip',
                'unrecognized ip',
                'unauthorized ip',
                'unauthorised ip',
                'ip address is not authorized',
                'ip address is not authorised',
            )
        )
        status, code = response.status_code, 'brevo_request_rejected'
        if status in (401, 403) and ip_blocked:
            code = 'brevo_ip_not_authorized'
            description = 'O Brevo bloqueou o IP deste servidor. Autorize a tentativa em Brevo → Configurações → Segurança → IPs autorizados e tente novamente.'
        elif status == 401:
            code = 'brevo_invalid_key'
            description = 'O Brevo não aceitou a chave de API. Copie uma chave de API ativa do Brevo; a chave SMTP não serve para esta conexão.'
        elif status == 403:
            code = 'brevo_permission_denied'
            description = 'O Brevo não autorizou esta operação. Confira as permissões da chave e os IPs autorizados na segurança da conta.'
        elif status == 429:
            code = 'brevo_rate_limited'
            description = 'O limite de requisições do Brevo foi atingido. Aguarde antes de tentar novamente.'
        elif status == 402:
            description = 'O Brevo informou que o saldo ou plano da conta não permite esta operação.'
        elif status >= 500:
            code = 'brevo_unavailable'
            description = (
                'O Brevo está temporariamente indisponível. Consulte o provedor antes de repetir uma operação de envio.'
            )
        else:
            description = 'O Brevo recusou os dados da solicitação. Confira o remetente e a configuração da conta.'
        current_app.logger.warning('Brevo recusou operação: http_status=%s reason=%s', status, code)
        # A rejected credential is a validation failure, not a broken gateway. Cloudflare replaces origin 502 bodies.
        raise APIError(description, 503 if status >= 500 else 429 if status == 429 else 422, code=code)
    try:
        result = response.json() if response.content else {}
    except ValueError:
        raise APIError(
            'O Brevo devolveu uma resposta inválida. Consulte o provedor antes de repetir.',
            503,
            code='brevo_invalid_response',
        ) from None
    if not isinstance(result, dict):
        raise APIError(
            'O Brevo devolveu uma resposta inválida. Consulte o provedor antes de repetir.',
            503,
            code='brevo_invalid_response',
        )
    return result


def connection(workspace_id):
    row = BrevoConnection.query.filter_by(workspace_id=workspace_id, active=True).first()
    if not row or not row.encrypted_key:
        raise APIError('Configure o Brevo em Configurações → Conexões.', 409)
    return row


def key_for(row):
    return cipher().decrypt(row.encrypted_key.encode()).decode()


def connect(workspace_id, data):
    row = BrevoConnection.query.filter_by(workspace_id=workspace_id).with_for_update().first()
    if (
        row
        and EmailCampaign.query.filter(
            EmailCampaign.workspace_id == workspace_id,
            EmailCampaign.channel == 'email',
            EmailCampaign.status.in_(('preparing', 'importing', 'sending')),
        ).first()
    ):
        raise APIError('Aguarde a operação de campanha em andamento antes de alterar a conexão.', 409)
    key = data.get('api_key')
    if key is not None:
        key = key.strip()
        if not key or not key.isascii() or any(char.isspace() for char in key):
            raise APIError('Cole somente a chave de API, sem espaços, quebras de linha ou o prefixo Bearer.', 422)
    else:
        key = key_for(row) if row and row.active else None
    if not key:
        raise APIError('Informe a chave de API do Brevo.', 422)
    api(key, 'account')
    senders = api(key, 'senders').get('senders') or []
    email = data['sender_email'].strip().lower()
    if not any(str(item.get('email', '')).lower() == email and item.get('active') for item in senders):
        raise APIError('Cadastre e valide este remetente no Brevo antes de conectar.', 422)
    if not row:
        row = BrevoConnection(workspace_id=workspace_id, webhook_secret=secrets.token_urlsafe(32))
        db.session.add(row)
    if row.encrypted_key and key != key_for(row):
        # Provider IDs belong to an account; never reuse them after changing credentials.
        row.folder_id, row.webhook_id = None, None
        row.version += 1
        row.webhook_secret = secrets.token_urlsafe(32)
    row.encrypted_key = cipher().encrypt(key.encode()).decode()
    row.sender_email, row.sender_name = email, data['sender_name']
    row.active, row.validated_at = True, now()
    db.session.flush()
    return row


def access_sender(workspace_id):
    config = current_app.config
    if config.get('BREVO_SYSTEM_API_KEY') and config.get('BREVO_SYSTEM_SENDER_EMAIL'):
        return config['BREVO_SYSTEM_API_KEY'], {
            'email': config['BREVO_SYSTEM_SENDER_EMAIL'],
            'name': config['BREVO_SYSTEM_SENDER_NAME'],
        }
    row = connection(workspace_id)
    return key_for(row), {'email': row.sender_email, 'name': row.sender_name}


def send_access(workspace_id, email, name, subject, content):
    key, sender = access_sender(workspace_id)
    result = api(
        key,
        'smtp/email',
        'POST',
        json={
            'sender': sender,
            'to': [{'email': email, 'name': name}],
            'subject': subject,
            'textContent': content,
            'tags': ['antares-access'],
        },
    )
    if not result.get('messageId'):
        raise APIError('O Brevo não confirmou o envio do e-mail.', 502)
    return result['messageId']


def setup_webhook(row):
    body = {
        'url': current_app.config['APP_URL'] + '/api/v1/brevo/webhook/' + row.id,
        'type': 'marketing',
        'description': 'Antares ' + row.workspace_id,
        'events': ['delivered', 'opened', 'click', 'hardBounce', 'softBounce', 'spam', 'unsubscribed'],
        'headers': [{'key': 'X-Brevo-Secret', 'value': row.webhook_secret}],
    }
    key = key_for(row)
    if row.webhook_id:
        api(key, 'webhooks/' + str(row.webhook_id), 'PUT', json=body)
    else:
        row.webhook_id = int(api(key, 'webhooks', 'POST', json=body)['id'])
    return row
