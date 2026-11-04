"""Instagram client: provider HTTP and credential primitives."""

import requests
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

from ...common import APIError


def configured():
    return all(
        current_app.config.get(k) for k in ('INSTAGRAM_APP_ID', 'INSTAGRAM_APP_SECRET', 'INSTAGRAM_ENCRYPTION_KEY')
    )


def cipher():
    return Fernet(current_app.config['INSTAGRAM_ENCRYPTION_KEY'].encode())


def graph(path, token, method='GET', **kwargs):
    url = 'https://graph.instagram.com/' + current_app.config['INSTAGRAM_API_VERSION'] + '/' + path
    try:
        response = requests.request(
            method, url, headers={'Authorization': 'Bearer ' + token}, timeout=(5, 20), **kwargs
        )
        data = response.json()
        if not response.ok or 'error' in data:
            raise APIError('O Instagram recusou a solicitação. Confira a autorização e as permissões da conta.', 502)
        return data
    except (requests.RequestException, ValueError):
        raise APIError('Não foi possível confirmar a solicitação no Instagram.', 502) from None


def profile(token):
    data = graph('me', token, params={'fields': 'id,user_id,username,name,profile_picture_url'})
    if not str(data.get('user_id', '')).isdigit() or not data.get('username'):
        raise APIError('O token não identificou uma conta profissional do Instagram.', 422)
    return data


def fetch_account(token):
    """Name, @username and picture of the connected account. Best effort with short timeouts."""
    try:
        response = requests.get(
            f'https://graph.instagram.com/{current_app.config["INSTAGRAM_API_VERSION"]}/me',
            params={'fields': 'user_id,username,name,profile_picture_url'},
            headers={'Authorization': 'Bearer ' + token},
            timeout=(2, 5),
        )
        data = response.json()
        return None if not response.ok or 'error' in data else data
    except (requests.RequestException, ValueError):
        return None


def oauth_tokens(code):
    try:
        response = requests.post(
            'https://api.instagram.com/oauth/access_token',
            data={
                'client_id': current_app.config['INSTAGRAM_APP_ID'],
                'client_secret': current_app.config['INSTAGRAM_APP_SECRET'],
                'grant_type': 'authorization_code',
                'redirect_uri': current_app.config['INSTAGRAM_REDIRECT_URI'],
                'code': code,
            },
            timeout=(5, 20),
        )
        data = response.json()
        if not response.ok or not data.get('access_token'):
            raise APIError('Não foi possível concluir a autorização do Instagram. Conecte novamente.', 502)
        response = requests.get(
            'https://graph.instagram.com/access_token',
            params={
                'grant_type': 'ig_exchange_token',
                'client_secret': current_app.config['INSTAGRAM_APP_SECRET'],
                'access_token': data['access_token'],
            },
            timeout=(5, 20),
        )
        result = response.json()
        if not response.ok or not result.get('access_token') or not result.get('expires_in'):
            raise APIError('Não foi possível obter a autorização de longa duração. Conecte novamente.', 502)
        return result
    except (requests.RequestException, ValueError):
        raise APIError('O Instagram não confirmou a autorização. Tente conectar novamente.', 502) from None


def fetch_profile(connection, scoped_id):
    """Name and @username of a person who messaged the account (User Profile API). Best effort, short timeouts."""
    try:
        token = cipher().decrypt(connection.encrypted_token.encode()).decode()
        response = requests.get(
            f'https://graph.instagram.com/{current_app.config["INSTAGRAM_API_VERSION"]}/{scoped_id}',
            params={'fields': 'name,username'},
            headers={'Authorization': 'Bearer ' + token},
            timeout=(2, 4),
        )
        data = response.json()
        if not response.ok or 'error' in data:
            return None
        name, username = (data.get('name') or '').strip(), (data.get('username') or '').strip()
        return {'name': name, 'username': username} if name or username else None
    except (requests.RequestException, ValueError, InvalidToken):
        return None
