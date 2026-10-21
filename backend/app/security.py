"""Production config checks, JWT callbacks and response security headers."""

import os

from flask import jsonify

from .access import workspace_role
from .extensions import db, jwt
from .models import User, Workspace

INSECURE_SECRET_PREFIXES = ('development-', 'replace-', 'change_me')


def validate_production_config(app):
    if os.getenv('APP_ENV') != 'production' or app.testing:
        return
    for key in ('SECRET_KEY', 'JWT_SECRET_KEY'):
        value = app.config[key]
        if value.lower().startswith(INSECURE_SECRET_PREFIXES) or len(value) < 32:
            raise RuntimeError(f'Configure {key} com pelo menos 32 caracteres aleatórios.')
    if not app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql'):
        raise RuntimeError('Produção requer PostgreSQL.')


def _unauthorized(code, message):
    return jsonify(error={'code': code, 'message': message}), 401


def register_jwt_callbacks():
    @jwt.unauthorized_loader
    def missing_token(reason):
        return _unauthorized('unauthorized', 'Autenticação necessária.')

    @jwt.invalid_token_loader
    def invalid_token(reason):
        return _unauthorized('invalid_token', 'Token inválido.')

    @jwt.expired_token_loader
    def expired_token(header, claims):
        return _unauthorized('expired_token', 'Sessão expirada.')

    @jwt.token_in_blocklist_loader
    def revoked(header, claims):
        user = db.session.get(User, claims['sub'])
        workspace = db.session.get(Workspace, claims.get('wid', user.workspace_id)) if user else None
        return not user or claims.get('ver') != user.token_version or not workspace_role(user, workspace)

    @jwt.revoked_token_loader
    def revoked_response(header, claims):
        return _unauthorized('revoked_token', 'Sessão revogada.')


def register_security_headers(app):
    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        if os.getenv('APP_ENV') == 'production':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response
