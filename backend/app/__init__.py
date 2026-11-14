from flask import Flask
from flask_cors import CORS

from .cli import register_commands
from .config import Config, TestingConfig
from .error_reporting import init_error_reporting
from .errors import register_error_handlers
from .extensions import db, jwt, limiter, migrate
from .observability import register_observability
from .security import register_jwt_callbacks, register_security_headers, validate_production_config


def create_app(config=None):
    app = Flask(__name__)
    testing = config == 'testing' or (isinstance(config, dict) and config.get('TESTING') is True)
    app.config.from_object(TestingConfig if testing else Config)
    if isinstance(config, dict):
        app.config.update(config)
    validate_production_config(app)
    init_error_reporting(app)
    register_observability(app)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)
    CORS(app, resources={r'/api/*': {'origins': app.config['ALLOWED_ORIGINS']}})

    from . import models  # noqa: F401  (registers the tables with SQLAlchemy)

    register_blueprints(app)
    from .routes.atlas import oauth_callback

    app.add_url_rule('/auth/callback', view_func=oauth_callback)
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
        atlas,
        auth,
        billing,
        booking,
        brevo,
        communications,
        contact_views,
        crm,
        domains,
        funnels,
        growth,
        history,
        instagram,
        instagram_content,
        mcp,
        operations,
        projects,
        reports,
        tasks,
        whatsapp,
    )

    for module in (
        atlas,
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
        billing,
        brevo,
        operations,
        contact_views,
        instagram,
        instagram_content,
        mcp,
        history,
        projects,
    ):
        app.register_blueprint(module.bp, url_prefix='/api/v1')
