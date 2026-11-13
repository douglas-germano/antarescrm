"""MCP over Streamable HTTP (stateless JSON responses) and the screens' API token management."""

import json

from flask import Blueprint, current_app, g, request

from ..common import APIError, audit, get, query, require
from ..extensions import db, limiter
from ..models import TOKEN_SCOPES, ApiToken, now
from ..services import api_tokens, mcp

bp = Blueprint('mcp', __name__)
SERVER = {'name': 'antares-crm', 'title': 'Antares CRM', 'version': '1.0.0'}


def rpc_error(identifier, code, message, status=200):
    return {'jsonrpc': '2.0', 'id': identifier, 'error': {'code': code, 'message': message}}, status


def tool_result(data, error=False):
    text = json.dumps(data, ensure_ascii=False, default=str)
    result = {'content': [{'type': 'text', 'text': text}], 'isError': error}
    if not error and isinstance(data, dict):
        result['structuredContent'] = data
    return result


@bp.route('/mcp', methods=['GET', 'DELETE'])
def mcp_stream():
    # Stateless server: no server-initiated stream and no sessions to end.
    return {'error': {'message': 'Use POST com JSON-RPC.'}}, 405, {'Allow': 'POST'}


@bp.post('/mcp')
@limiter.limit('240 per minute')
def mcp_endpoint():
    origin = request.headers.get('Origin')
    if origin and origin.rstrip('/') != current_app.config['APP_URL']:
        return {'error': {'message': 'Origem não permitida.'}}, 403
    try:
        token, user, workspace, role = api_tokens.authenticate(request.headers.get('Authorization'))
    except APIError as error:
        return (
            {'error': {'message': error.message}},
            401,
            {'WWW-Authenticate': 'Bearer realm="antares", error="invalid_token"'},
        )
    g.user, g.workspace_id, g.role, g.api_token = user, workspace.id, role, token
    message = request.get_json(silent=True)
    if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or not isinstance(message.get('method'), str):
        return rpc_error(None, -32600, 'Requisição JSON-RPC inválida.', 400)
    identifier, method, params = message.get('id'), message['method'], message.get('params') or {}
    if not isinstance(params, dict):
        return rpc_error(identifier, -32602, 'params deve ser um objeto.')
    if 'id' not in message:
        return '', 202  # Notifications (e.g. notifications/initialized) need no answer.
    if method == 'initialize':
        asked = params.get('protocolVersion')
        version = asked if asked in mcp.PROTOCOL_VERSIONS else mcp.PROTOCOL_VERSIONS[0]
        return {
            'jsonrpc': '2.0',
            'id': identifier,
            'result': {
                'protocolVersion': version,
                'capabilities': {'tools': {'listChanged': False}},
                'serverInfo': SERVER,
                'instructions': mcp.INSTRUCTIONS,
            },
        }
    if method == 'ping':
        return {'jsonrpc': '2.0', 'id': identifier, 'result': {}}
    if method == 'tools/list':
        return {'jsonrpc': '2.0', 'id': identifier, 'result': {'tools': mcp.visible_tools()}}
    if method != 'tools/call':
        return rpc_error(identifier, -32601, 'Método não suportado: ' + method[:80])
    name, arguments = params.get('name'), params.get('arguments') or {}
    entry = mcp.TOOLS.get(name)
    if not entry or entry['spec'] not in mcp.visible_tools():
        return rpc_error(identifier, -32602, 'Ferramenta desconhecida ou sem permissão: ' + str(name)[:80])
    if not isinstance(arguments, dict):
        return rpc_error(identifier, -32602, 'arguments deve ser um objeto.')
    try:
        result = tool_result(entry['handler'](arguments))
    except APIError as error:
        db.session.rollback()
        result = tool_result({'error': error.message, 'status': error.status}, error=True)
    except Exception as error:  # tool boundary: report to the AI without internals
        db.session.rollback()
        current_app.logger.warning('mcp_tool_failed tool=%s type=%s', name, type(error).__name__)
        result = tool_result({'error': 'Falha inesperada no Antares. Tente novamente.'}, error=True)
    return {'jsonrpc': '2.0', 'id': identifier, 'result': result}


# ---------- token management (screens) ----------
def public(row):
    return {**row.to_dict(), 'active': not row.revoked_at and (not row.expires_at or row.expires_at > now())}


@bp.get('/api-tokens')
@require('owner', 'admin')
def tokens():
    rows = query(ApiToken).order_by(ApiToken.created_at.desc()).all()
    return {
        'items': [public(row) for row in rows],
        'scopes': TOKEN_SCOPES,
        'durations': list(api_tokens.DURATIONS),
        'endpoint': current_app.config['APP_URL'] + '/mcp',
    }


@bp.post('/api-tokens')
@require('owner', 'admin')
@limiter.limit('20 per hour')
def token_create():
    data = request.get_json(silent=True) or {}
    row, secret = api_tokens.create(
        g.workspace_id, g.user.id, data.get('name'), data.get('scopes'), data.get('days', 90)
    )
    audit('api_token.create', row, {'scopes': row.scopes})
    db.session.commit()
    return {**public(row), 'token': secret}, 201


@bp.delete('/api-tokens/<uuid:token_id>')
@require('owner', 'admin')
def token_revoke(token_id):
    row = get(ApiToken, token_id, lock=True)
    if not row.revoked_at:
        row.revoked_at = now()
        audit('api_token.revoke', row)
        db.session.commit()
    return public(row)
