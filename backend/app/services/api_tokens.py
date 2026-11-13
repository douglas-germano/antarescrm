"""API tokens: creation, authentication and per-token limits for irreversible actions."""

import hashlib
import secrets
from datetime import timedelta

from ..access import workspace_role
from ..common import APIError
from ..extensions import db
from ..models import TOKEN_SCOPES, ApiToken, AuditLog, User, Workspace, now

PREFIX = 'antares_'
DURATIONS = (30, 90, 180, 365)
ACTIONS_PER_HOUR = 60  # Sends, publications and comment replies per token.


def digest(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


def create(workspace_id, user_id, name, scopes, days):
    name = (name or '').strip()
    if not 1 <= len(name) <= 120:
        raise APIError('Dê um nome ao token, com até 120 caracteres.', 422)
    if not isinstance(scopes, list) or not scopes or any(scope not in TOKEN_SCOPES for scope in scopes):
        raise APIError('Escolha ao menos uma permissão válida.', 422)
    if days not in DURATIONS:
        raise APIError('Validade inválida.', 422)
    secret = PREFIX + secrets.token_urlsafe(32)
    row = ApiToken(
        workspace_id=workspace_id,
        user_id=user_id,
        name=name,
        prefix=secret[: len(PREFIX) + 4],
        token_hash=digest(secret),
        scopes=sorted(set(scopes)),
        expires_at=now() + timedelta(days=days),
    )
    db.session.add(row)
    db.session.flush()
    return row, secret


def authenticate(header):
    """Returns (token, user, workspace, role) for a valid `Authorization: Bearer antares_...` header."""
    secret = header[7:].strip() if isinstance(header, str) and header[:7].lower() == 'bearer ' else ''
    if not secret.startswith(PREFIX) or len(secret) > 200:
        raise APIError('Informe um token do Antares no cabeçalho Authorization.', 401)
    row = ApiToken.query.filter_by(token_hash=digest(secret)).first()
    if not row or row.revoked_at or (row.expires_at and row.expires_at <= now()):
        raise APIError('Token inválido, expirado ou revogado.', 401)
    user, workspace = db.session.get(User, row.user_id), db.session.get(Workspace, row.workspace_id)
    role = workspace_role(user, workspace) if user and user.active and workspace and workspace.active else None
    if not role:
        raise APIError('Quem criou este token não tem mais acesso à conta.', 401)
    if not row.last_used_at or row.last_used_at < now() - timedelta(minutes=1):
        row.last_used_at = now()
        db.session.commit()
    return row, user, workspace, role


def check_budget(row):
    used = AuditLog.query.filter(
        AuditLog.resource == 'api_tokens',
        AuditLog.resource_id == row.id,
        AuditLog.action.like('mcp.action.%'),
        AuditLog.created_at > now() - timedelta(hours=1),
    ).count()
    if used >= ACTIONS_PER_HOUR:
        raise APIError(f'Limite de {ACTIONS_PER_HOUR} ações por hora deste token atingido.', 429)
