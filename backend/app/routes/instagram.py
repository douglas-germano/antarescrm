import hashlib
import hmac
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from flask import Blueprint, current_app, g, request

from ..common import APIError, query, require
from ..extensions import db, limiter
from ..models import InstagramConnection, InstagramOAuthState, now
from ..services import instagram as service

bp = Blueprint('instagram', __name__)

SCOPES = (
    'instagram_business_basic',
    'instagram_business_manage_messages',
    'instagram_business_manage_comments',
    'instagram_business_content_publish',
    'instagram_business_manage_insights',
)


def chosen(data=None):
    """The account a request acts on: `connection_id` from the body or query, else the oldest usable one."""
    data = data if data is not None else (request.get_json(silent=True) or {})
    identifier = data.get('connection_id') or request.args.get('connection_id')
    if identifier is not None and not isinstance(identifier, str):
        raise APIError('Conta inválida.', 422)
    return identifier


def describe(row):
    return {**row.to_dict(), 'connected': service.usable(row)}


@bp.get('/instagram/connection')
@require('owner', 'admin')
def connection():
    """All Instagram profiles of this workspace. `connection` keeps the first one for older screens."""
    rows = query(InstagramConnection).order_by(InstagramConnection.created_at, InstagramConnection.id).all()
    rows = [row for row in rows if row.active] + [row for row in rows if not row.active]
    if service.configured():
        for row in rows:
            service.refresh_account(row)
    items = [describe(row) for row in rows]
    first = next((item for item in items if item['connected']), items[0] if items else None)
    return {
        'configured': service.configured(),
        'connection': first,
        'connections': items,
        'connected': any(item['connected'] for item in items),
    }


@bp.get('/instagram/accounts')
@require()
def accounts():
    """Connected profiles for the publishing and metrics screens, available to the whole team."""
    rows = (
        query(InstagramConnection)
        .filter_by(active=True)
        .order_by(InstagramConnection.created_at, InstagramConnection.id)
        .all()
    )
    keys = ('id', 'username', 'name', 'profile_picture_url', 'expires_at', 'can_publish', 'can_read_insights')
    return {'items': [{key: describe(row)[key] for key in (*keys, 'connected')} for row in rows]}


@bp.post('/instagram/connect')
@require('owner', 'admin')
@limiter.limit('10 per minute')
def start():
    if not service.configured():
        raise APIError('Configure o aplicativo Instagram no servidor.', 503)
    state = secrets.token_urlsafe(32)
    db.session.add(
        InstagramOAuthState(
            workspace_id=g.workspace_id,
            user_id=g.user.id,
            state_hash=hashlib.sha256(state.encode()).hexdigest(),
            expires_at=now() + timedelta(minutes=10),
        )
    )
    db.session.commit()
    return {
        'url': 'https://www.instagram.com/oauth/authorize?'
        + urlencode(
            {
                'client_id': current_app.config['INSTAGRAM_APP_ID'],
                'redirect_uri': current_app.config['INSTAGRAM_REDIRECT_URI'],
                'scope': ','.join(SCOPES),
                'response_type': 'code',
                'state': state,
                'enable_fb_login': '0',
                'force_authentication': '1',
            }
        )
    }


@bp.post('/instagram/complete')
@require('owner', 'admin')
@limiter.limit('10 per minute')
def complete():
    data = request.get_json(silent=True) or {}
    state, code = data.get('state'), data.get('code')
    if not isinstance(state, str) or not isinstance(code, str) or not 1 <= len(code) <= 4096 or len(state) > 200:
        raise APIError('Autorização inválida.', 422)
    row = (
        query(InstagramOAuthState)
        .filter_by(user_id=g.user.id, state_hash=hashlib.sha256(state.encode()).hexdigest())
        .with_for_update()
        .first()
    )
    if not row or row.consumed or row.expires_at <= now():
        raise APIError('Autorização expirada ou já utilizada. Conecte novamente.', 409)
    row.consumed = True
    db.session.commit()  # Consume even on failed exchange; do not reuse provider authorization codes.
    result = service.oauth_tokens(code)
    # Instagram Login grants the requested set as a whole; record it when the response omits it.
    connection = service.connect(
        g.workspace_id, result['access_token'], result['expires_in'], result.get('permissions') or ','.join(SCOPES)
    )
    db.session.commit()
    try:
        service.subscribe(connection)  # Without this the Instagram Login API never delivers message webhooks.
        subscribed = True
    except APIError:
        subscribed = False  # Connection stays valid; "Verificar recebimento" retries and explains.
    return {**connection.to_dict(), 'subscribed': subscribed}


@bp.post('/instagram/verify')
@require('owner', 'admin')
@limiter.limit('10 per minute')
def verify():
    row = service.active_connection(g.workspace_id, chosen())
    return service.verify_delivery(row)


@bp.post('/instagram/disconnect')
@require('owner', 'admin')
def disconnect():
    identifier = chosen()
    row = (
        query(InstagramConnection).filter_by(id=identifier).first()
        if identifier
        else query(InstagramConnection).filter_by(active=True).order_by(InstagramConnection.created_at).first()
    )
    if row:
        row.active, row.encrypted_token = False, ''
        db.session.commit()
    return {'disconnected': True}


@bp.post('/instagram/refresh')
@require('owner', 'admin')
@limiter.limit('2 per hour')
def refresh():
    row = service.active_connection(g.workspace_id, chosen())
    token = service.cipher().decrypt(row.encrypted_token.encode()).decode()
    # Refresh is explicit; provider errors and credentials are never returned to the browser.

    try:
        response = requests.get(
            'https://graph.instagram.com/refresh_access_token',
            params={'grant_type': 'ig_refresh_token', 'access_token': token},
            timeout=(5, 20),
        )
        data = response.json()
        if not response.ok or not data.get('access_token') or not data.get('expires_in'):
            raise APIError('O Instagram não renovou a autorização. Reconecte o perfil se necessário.', 502)
    except (requests.RequestException, ValueError):
        raise APIError('Não foi possível renovar a autorização.', 502) from None
    service.connect(g.workspace_id, data['access_token'], data['expires_in'])
    db.session.commit()
    return {'refreshed': True}


@bp.post('/instagram/webhook')
def webhook():
    log = current_app.logger
    secret = current_app.config.get('INSTAGRAM_APP_SECRET')
    if not secret:
        log.warning('instagram webhook: rejected, app secret not configured')
        raise APIError('Instagram indisponível.', 503)
    raw = request.get_data()
    expected = 'sha256=' + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, request.headers.get('X-Hub-Signature-256', '')):
        log.warning('instagram webhook: rejected, invalid signature (%d bytes)', len(raw))
        raise APIError('Assinatura inválida.', 401)
    if not request.is_json:
        log.warning('instagram webhook: rejected, not JSON')
        raise APIError('Envie JSON.', 415)
    body = request.get_json(silent=True)
    # Metadata only: never the message text, sender ids or tokens.
    entries = body.get('entry') if isinstance(body, dict) and isinstance(body.get('entry'), list) else []
    summary = [
        {
            'account': str(e.get('id')),
            'messaging': len(e.get('messaging') or []),
            'changes': [str(c.get('field')) for c in (e.get('changes') or [])],
        }
        for e in entries
        if isinstance(e, dict)
    ]
    try:
        service.receive(body)
        db.session.commit()
    except APIError as error:
        log.warning('instagram webhook: failed (%s) %s', error.message, summary)
        raise
    log.warning('instagram webhook: accepted %s', summary)
    return {'received': True}
