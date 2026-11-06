"""OAuth public-client flow with encrypted, database-backed sessions."""

import base64
import hashlib
import json
import re
from datetime import timedelta
from secrets import token_urlsafe
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import jwt
import requests
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

from ..common import APIError
from ..extensions import db
from ..models import AtlasConnection, AtlasCredential, now
from .booking import lock

ISSUER = 'https://auth.openai.com'
RESOURCE = 'https://api.openai.com/v1'
SCOPES = 'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'
REQUIRED = {'resource.invoke', 'chatgpt.tokens.use.direct'}
PREFIX = 'fernet-v1:'


def cipher(workspace_id):
    row = AtlasConnection.query.filter_by(workspace_id=workspace_id).first()
    key = row.oauth_key if row and row.oauth_key else current_app.config.get('ATLAS_ENCRYPTION_KEY')
    try:
        return Fernet(key or '')
    except (TypeError, ValueError):
        raise APIError('Configure a chave de criptografia do Atlas.', 503) from None


def encrypt(workspace_id, value):
    return cipher(workspace_id).encrypt(json.dumps(value).encode()).decode()


def decrypt(workspace_id, value):
    try:
        return json.loads(cipher(workspace_id).decrypt(value.encode()))
    except (InvalidToken, ValueError):
        raise APIError('Não foi possível abrir a conexão criptografada do Atlas.', 503) from None


def callback_uri():
    try:
        port = int(current_app.config['ATLAS_CALLBACK_PORT'])
        if not 1 <= port <= 65535:
            raise ValueError
    except (TypeError, ValueError):
        raise APIError('A porta local do Atlas é inválida.', 503) from None
    return f'http://127.0.0.1:{port}/auth/callback'


def credential(workspace_id):
    return AtlasCredential.query.filter_by(workspace_id=workspace_id).first()


def session(workspace_id):
    row = credential(workspace_id)
    return (
        decrypt(workspace_id, row.ciphertext.removeprefix(PREFIX))
        if row and row.ciphertext.startswith(PREFIX)
        else None
    )


def save(workspace_id, value):
    ciphertext = PREFIX + encrypt(workspace_id, value)
    row = credential(workspace_id)
    if row is None:
        row = AtlasCredential(workspace_id=workspace_id, version=0)
        db.session.add(row)
    row.ciphertext, row.version = ciphertext, row.version + 1


def status(workspace_id):
    row = AtlasConnection.query.filter_by(workspace_id=workspace_id).first()
    try:
        callback_uri()
        connection = session(workspace_id)
    except APIError:
        return {'available': False, 'connected': False, 'state': 'idle'}
    pending = row and row.oauth_attempt
    state = 'authorizing' if pending and row.expires_at > now() else 'idle'
    if row and (row.state == 'failed' or (pending and row.expires_at <= now())):
        state = 'failed'
    return {'available': True, 'connected': bool(connection and not connection.get('revoked')), 'state': state}


def start(account):
    lock('atlas-oauth:' + account.workspace_id)
    row = AtlasConnection.query.filter_by(workspace_id=account.workspace_id).first()
    if row is None:
        row = AtlasConnection(workspace_id=account.workspace_id, state='authorizing')
        db.session.add(row)
    previous = session(account.workspace_id)
    if not row.oauth_key:
        row.oauth_key = current_app.config['ATLAS_ENCRYPTION_KEY'] if previous else Fernet.generate_key().decode()
    state, nonce, verifier = (token_urlsafe(32) for _ in range(3))
    redirect = callback_uri()
    row.oauth_host = row.oauth_host or f'urn:uuid:{uuid4()}'
    row.oauth_state = hashlib.sha256(state.encode()).hexdigest()
    row.oauth_attempt = encrypt(
        account.workspace_id,
        {
            'nonce': nonce,
            'verifier': verifier,
            'redirect': redirect,
            'user_id': account.user_id,
            'client_id': previous['client_id'] if previous else None,
            'subject': previous['subject'] if previous else None,
        },
    )
    row.expires_at, row.state = now() + timedelta(minutes=5), 'authorizing'
    params = {
        'client_id': previous['client_id'] if previous else 'dynamic_agent_client',
        'ext_agent_host_id': row.oauth_host,
        'response_type': 'code',
        'redirect_uri': redirect,
        'scope': SCOPES,
        'resource': RESOURCE,
        'state': state,
        'nonce': nonce,
        'code_challenge_method': 'S256',
        'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='),
    }
    if previous:
        params['prompt'] = 'consent'
    else:
        params['agent_name_hint'] = 'Antares CRM'
    db.session.commit()
    return ISSUER + '/api/accounts/authorize?' + urlencode(params)


def provider_json(url, **kwargs):
    try:
        response = requests.request(kwargs.pop('method', 'GET'), url, timeout=(3, 8), allow_redirects=False, **kwargs)
        if response.status_code != 200:
            if response.status_code == 400 and response.json().get('error') == 'invalid_grant':
                raise APIError('Reconecte o plano ChatGPT.', 409)
            raise ValueError
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError
        return data
    except (requests.RequestException, ValueError, AttributeError):
        raise APIError('Não foi possível completar a solicitação ao ChatGPT.', 502) from None


def identity(token, client_id, nonce=None, received_at=None):
    discovery = provider_json(ISSUER + '/.well-known/openid-configuration')
    uri = discovery.get('jwks_uri')
    if (
        discovery.get('issuer') != ISSUER
        or not isinstance(uri, str)
        or urlsplit(uri).netloc != 'auth.openai.com'
        or urlsplit(uri).scheme != 'https'
    ):
        raise APIError('Não foi possível verificar a identidade do ChatGPT.', 502)
    keys = provider_json(uri).get('keys', [])
    try:
        header = jwt.get_unverified_header(token)
        key = next(key for key in keys if key.get('kid') == header['kid'])
        claims = jwt.decode(
            token,
            jwt.PyJWK.from_dict(key, algorithm='RS256').key,
            algorithms=['RS256'],
            issuer=ISSUER,
            audience=client_id,
            leeway=5,
            options={'require': ['iss', 'aud', 'exp', 'iat', 'sub'], 'verify_exp': received_at is None},
        )
        if (
            (nonce is not None and claims.get('nonce') != nonce)
            or (received_at is not None and not int(claims['iat']) - 5 <= received_at < int(claims['exp']) + 5)
            or not claims['sub']
            or claims.get('azp', client_id) != client_id
            or (isinstance(claims['aud'], list) and len(claims['aud']) > 1 and claims.get('azp') != client_id)
        ):
            raise ValueError
        return claims['sub']
    except (jwt.PyJWTError, KeyError, TypeError, StopIteration, ValueError):
        raise APIError('Identidade do ChatGPT inválida.', 409) from None


def tokens(data, scopes=None):
    scope = data.get('scope', scopes)
    expires = data.get('expires_in')
    if (
        not isinstance(scope, str)
        or not REQUIRED.issubset(scope.split())
        or not isinstance(expires, (int, float))
        or not 0 < expires <= 86400
        or not all(isinstance(data.get(key), str) and data[key] for key in ('access_token', 'refresh_token'))
    ):
        raise APIError('O ChatGPT não autorizou o uso renovável do plano.', 409)
    return {
        'access_token': data['access_token'],
        'refresh_token': data['refresh_token'],
        'scope': scope,
        'expires_at': (now() + timedelta(seconds=expires)).timestamp(),
    }


def exchange(**data):
    return provider_json(ISSUER + '/api/accounts/oauth/token', method='POST', data={**data, 'resource': RESOURCE})


def callback(query, host):
    state = query.get('state', '')
    if host != urlsplit(callback_uri()).netloc or not re.fullmatch(r'[A-Za-z0-9_-]{43}', state):
        return False
    digest = hashlib.sha256(state.encode()).hexdigest()
    row = AtlasConnection.query.filter_by(oauth_state=digest).first()
    if row is None:
        return False
    workspace_id = row.workspace_id
    lock('atlas-oauth:' + workspace_id)
    db.session.refresh(row)
    if row.oauth_state != digest or not row.oauth_attempt or row.expires_at <= now():
        return False
    attempt = decrypt(workspace_id, row.oauth_attempt)
    row.oauth_attempt, row.state = None, 'failed'
    db.session.commit()  # Consume the callback before exchanging its one-time code.
    try:
        from .atlas import operator

        operator(workspace_id, attempt['user_id'])
        client_id = query.get('client_id') or attempt['client_id'] or ''
        code = query.get('code', '')
        if (
            query.get('error')
            or not code
            or len(code) > 4096
            or not re.fullmatch(r'oaiapp_[A-Za-z0-9_-]{1,190}', client_id)
            or (attempt['client_id'] and attempt['client_id'] != client_id)
        ):
            return False
        data = exchange(
            grant_type='authorization_code',
            client_id=client_id,
            code=code,
            code_verifier=attempt['verifier'],
            redirect_uri=attempt['redirect'],
        )
        subject = identity(data.get('id_token'), client_id, attempt['nonce'])
        if attempt['subject'] and subject != attempt['subject']:
            return False
        value = {**tokens(data), 'client_id': client_id, 'subject': subject}
        lock('atlas-oauth:' + workspace_id)
        db.session.refresh(row)
        if row.oauth_state != digest:
            return False
        operator(workspace_id, attempt['user_id'])
        save(workspace_id, value)
        row.oauth_state, row.state, row.connected = None, 'idle', True
        db.session.commit()
        return True
    except APIError:
        db.session.rollback()
        return False


def access_token(workspace_id):
    lock_key = 'atlas-oauth:' + workspace_id
    lock(lock_key)
    value = session(workspace_id)
    if not value or value.get('revoked'):
        raise APIError('Conecte o ChatGPT nas configurações do Atlas.', 409)
    try:
        if not value.get('pending') and value['expires_at'] <= now().timestamp() + 30:
            data = exchange(
                grant_type='refresh_token', client_id=value['client_id'], refresh_token=value['refresh_token']
            )
            rotated = tokens(data, value['scope'])
            if 'id_token' in data:
                value['pending'] = {'tokens': rotated, 'id_token': data['id_token'], 'received_at': now().timestamp()}
                save(workspace_id, value)
                db.session.commit()  # Persist the rotation before fetching signing keys.
                lock(lock_key)
                value = session(workspace_id)
            else:
                value.update(rotated)
                save(workspace_id, value)
        if value.get('revoked'):
            raise APIError('Reconecte o plano ChatGPT.', 409)
        if pending := value.get('pending'):
            subject = identity(pending['id_token'], value['client_id'], received_at=pending['received_at'])
            if subject != value['subject']:
                raise APIError('A conta do ChatGPT mudou. Reconecte o plano.', 409)
            value.update(value.pop('pending')['tokens'])
            save(workspace_id, value)
    except APIError as error:
        if error.status == 409:
            value['revoked'] = True
            value.pop('pending', None)
            row = AtlasConnection.query.filter_by(workspace_id=workspace_id).first()
            if row is not None:
                row.connected = False
            save(workspace_id, value)
            db.session.commit()
        raise
    db.session.commit()
    return value['access_token']
