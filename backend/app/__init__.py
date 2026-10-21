import os
import click
from flask import Flask, jsonify
from flask_cors import CORS
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException
from .config import Config, TestingConfig
from .extensions import db, migrate, jwt, limiter


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(TestingConfig if config == 'testing' else Config)
    if isinstance(config, dict):
        app.config.update(config)
    if os.getenv('APP_ENV') == 'production' and not app.testing:
        for key in ('SECRET_KEY', 'JWT_SECRET_KEY'):
            value = app.config[key]
            if value.lower().startswith(('development-', 'replace-', 'change_me')) or len(value) < 32:
                raise RuntimeError(f'Configure {key} com pelo menos 32 caracteres aleatórios.')
        if not app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql'):
            raise RuntimeError('Produção requer PostgreSQL.')
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)
    CORS(app, resources={r'/api/*': {'origins': app.config['ALLOWED_ORIGINS']}})
    from . import models
    from .routes import auth, crm, tasks, reports, whatsapp, agency, growth, communications, booking, operations, contact_views, instagram, projects
    for module in (auth, crm, tasks, reports, whatsapp, agency, growth, communications, booking, operations, contact_views, instagram, projects):
        app.register_blueprint(module.bp, url_prefix='/api/v1')

    @app.errorhandler(ValidationError)
    def validation_error(error):
        db.session.rollback()
        return jsonify(error={'code': 'validation_error', 'message': 'Revise os campos informados.', 'details': error.messages}), 422

    from .common import APIError

    @app.errorhandler(APIError)
    def api_error(error):
        db.session.rollback()
        return jsonify(error={'code': error.code, 'message': error.message, 'details': error.details}), error.status

    @app.errorhandler(IntegrityError)
    def integrity_error(error):
        db.session.rollback()
        return jsonify(error={'code': 'conflict', 'message': 'O registro já existe ou possui vínculos que impedem esta operação.'}), 409

    @app.errorhandler(HTTPException)
    def http_error(error):
        db.session.rollback()
        return jsonify(error={'code': error.name, 'message': error.description}), error.code

    @app.errorhandler(Exception)
    def internal_error(error):
        db.session.rollback()
        app.logger.exception('Erro não tratado')
        return jsonify(error={'code': 'internal_error', 'message': 'Não foi possível concluir a operação.'}), 500

    @jwt.unauthorized_loader
    def missing_token(reason):
        return jsonify(error={'code': 'unauthorized', 'message': 'Autenticação necessária.'}), 401

    @jwt.invalid_token_loader
    def invalid_token(reason):
        return jsonify(error={'code': 'invalid_token', 'message': 'Token inválido.'}), 401

    @jwt.expired_token_loader
    def expired_token(header, claims):
        return jsonify(error={'code': 'expired_token', 'message': 'Sessão expirada.'}), 401

    @jwt.token_in_blocklist_loader
    def revoked(header, claims):
        user = db.session.get(models.User, claims['sub'])
        from .access import workspace_role
        workspace = db.session.get(models.Workspace, claims.get('wid', user.workspace_id)) if user else None
        return not user or claims.get('ver') != user.token_version or not workspace_role(user, workspace)

    @jwt.revoked_token_loader
    def revoked_response(header, claims):
        return jsonify(error={'code': 'revoked_token', 'message': 'Sessão revogada.'}), 401

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        if os.getenv('APP_ENV') == 'production':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    @app.get('/api/v1/health')
    def health():
        db.session.execute(db.text('SELECT 1'))
        return {'status': 'ok', 'service': 'antarescrm', 'version': '1.0.0'}

    from .cli import register_commands
    register_commands(app)
    return app
