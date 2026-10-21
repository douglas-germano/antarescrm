from flask import Flask
from flask_cors import CORS

from .cli import register_commands
from .config import Config, TestingConfig
from .errors import register_error_handlers
from .extensions import db, jwt, limiter, migrate
from .security import register_jwt_callbacks, register_security_headers, validate_production_config


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(TestingConfig if config == 'testing' else Config)
    if isinstance(config, dict):
        app.config.update(config)
    validate_production_config(app)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)
    CORS(app, resources={r'/api/*': {'origins': app.config['ALLOWED_ORIGINS']}})

    from . import models  # noqa: F401  (registers the tables with SQLAlchemy)

    register_blueprints(app)
    register_error_handlers(app)
    register_jwt_callbacks()
    register_security_headers(app)
    register_commands(app)

    @app.get('/api/v1/health')
    def health():
        db.session.execute(db.text('SELECT 1'))
        return {'status': 'ok', 'service': 'antarescrm', 'version': '1.0.0'}

    return app


def register_blueprints(app):
    from .routes import (
        agency,
        auth,
        booking,
        communications,
        contact_views,
        crm,
        domains,
        funnels,
        growth,
        instagram,
        operations,
        projects,
        reports,
        tasks,
        whatsapp,
    )

    for module in (
        auth,
        crm,
        tasks,
        reports,
        whatsapp,
        agency,
        growth,
        funnels,
        domains,
        communications,
        booking,
        operations,
        contact_views,
        instagram,
        projects,
    ):
        app.register_blueprint(module.bp, url_prefix='/api/v1')
