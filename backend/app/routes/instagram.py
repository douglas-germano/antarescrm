import hashlib
import hmac
import secrets
from datetime import timedelta
from urllib.parse import urlencode
from flask import Blueprint, current_app, g, request
from ..common import require, APIError, query
from ..extensions import db, limiter
from ..models import InstagramConnection, InstagramOAuthState, now
from ..services import instagram as service

bp = Blueprint('instagram', __name__)


@bp.get('/instagram/connection')
@require('owner', 'admin')
def connection():
    row = query(InstagramConnection).first()
    if service.configured():
        service.refresh_account(row)
    return {'configured': service.configured(), 'connection': row.to_dict() if row else None,
        'connected': bool(row and row.active and (not row.expires_at or row.expires_at > now()))}


@bp.post('/instagram/connect')
@require('owner', 'admin')
@limiter.limit('10 per minute')
def start():
    if not service.configured(): raise APIError('Configure o aplicativo Instagram no servidor.', 503)
    state = secrets.token_urlsafe(32)
    db.session.add(InstagramOAuthState(workspace_id=g.workspace_id, user_id=g.user.id,
        state_hash=hashlib.sha256(state.encode()).hexdigest(), expires_at=now() + timedelta(minutes=10)))
    db.session.commit()
    return {'url': 'https://www.instagram.com/oauth/authorize?' + urlencode({
        'client_id': current_app.config['INSTAGRAM_APP_ID'], 'redirect_uri': current_app.config['INSTAGRAM_REDIRECT_URI'],
        'scope': 'instagram_business_basic,instagram_business_manage_messages,instagram_business_manage_comments',
        'response_type': 'code', 'state': state, 'enable_fb_login': '0', 'force_authentication': '1',
    })}


@bp.post('/instagram/complete')
@require('owner', 'admin')
@limiter.limit('10 per minute')
def complete():
    data = request.get_json(silent=True) or {}
    state, code = data.get('state'), data.get('code')
    if not isinstance(state, str) or not isinstance(code, str) or not 1 <= len(code) <= 4096 or len(state) > 200:
        raise APIError('Autorização inválida.', 422)
    row = query(InstagramOAuthState).filter_by(user_id=g.user.id, state_hash=hashlib.sha256(state.encode()).hexdigest()).with_for_update().first()
    if not row or row.consumed or row.expires_at <= now(): raise APIError('Autorização expirada ou já utilizada. Conecte novamente.', 409)
    row.consumed = True
    db.session.commit()  # Consume even on failed exchange; do not reuse provider authorization codes.
    result = service.oauth_tokens(code)
    connection = service.connect(g.workspace_id, result['access_token'], result['expires_in'])
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
    row = service.active_connection(g.workspace_id)
    return service.verify_delivery(row)


@bp.post('/instagram/disconnect')
@require('owner', 'admin')
def disconnect():
    row = query(InstagramConnection).first()
    if row:
        row.active, row.encrypted_token = False, ''
        db.session.commit()
    return {'disconnected': True}


@bp.post('/instagram/refresh')
@require('owner', 'admin')
@limiter.limit('2 per hour')
def refresh():
    row = service.active_connection(g.workspace_id)
    token = service.cipher().decrypt(row.encrypted_token.encode()).decode()
    # Refresh is explicit; provider errors and credentials are never returned to the browser.
    import requests
    try:
        response = requests.get('https://graph.instagram.com/refresh_access_token',
            params={'grant_type': 'ig_refresh_token', 'access_token': token}, timeout=(5, 20))
        data = response.json()
        if not response.ok or not data.get('access_token') or not data.get('expires_in'):
            raise APIError('O Instagram não renovou a autorização. Reconecte o perfil se necessário.', 502)
    except (requests.RequestException, ValueError):
        raise APIError('Não foi possível renovar a autorização.', 502)
    service.connect(g.workspace_id, data['access_token'], data['expires_in']); db.session.commit()
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
    summary = [{'account': str(e.get('id')), 'messaging': len(e.get('messaging') or []), 'changes': [str(c.get('field')) for c in (e.get('changes') or [])]} for e in entries if isinstance(e, dict)]
    try:
        service.receive(body)
        db.session.commit()
    except APIError as error:
        log.warning('instagram webhook: failed (%s) %s', error.message, summary)
        raise
    log.warning('instagram webhook: accepted %s', summary)
    return {'received': True}
