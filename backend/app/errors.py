"""JSON error responses shared by every endpoint."""

from flask import jsonify
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException

from .common import APIError
from .extensions import db


def register_error_handlers(app):
    @app.errorhandler(ValidationError)
    def validation_error(error):
        db.session.rollback()
        return jsonify(
            error={'code': 'validation_error', 'message': 'Revise os campos informados.', 'details': error.messages}
        ), 422

    @app.errorhandler(APIError)
    def api_error(error):
        db.session.rollback()
        return jsonify(error={'code': error.code, 'message': error.message, 'details': error.details}), error.status

    @app.errorhandler(IntegrityError)
    def integrity_error(error):
        db.session.rollback()
        return jsonify(
            error={'code': 'conflict', 'message': 'O registro já existe ou possui vínculos que impedem esta operação.'}
        ), 409

    @app.errorhandler(HTTPException)
    def http_error(error):
        db.session.rollback()
        return jsonify(error={'code': error.name, 'message': error.description}), error.code

    @app.errorhandler(Exception)
    def internal_error(error):
        db.session.rollback()
        app.logger.exception('Erro não tratado')
        return jsonify(error={'code': 'internal_error', 'message': 'Não foi possível concluir a operação.'}), 500
