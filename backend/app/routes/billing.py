from flask import Blueprint, current_app, g, request
from marshmallow import fields as f
from marshmallow import validate

from ..common import APIError, audit, payload, require
from ..extensions import db, limiter
from ..models import Workspace
from ..schemas import StrictSchema
from ..services import billing

bp = Blueprint('billing', __name__)


class SubscribeSchema(StrictSchema):
    cpf_cnpj = f.String(required=True, validate=validate.Length(min=11, max=18))


@bp.get('/billing')
@require()
def status():
    return billing.status_payload(db.session.get(Workspace, g.workspace_id))


@bp.post('/billing/subscribe')
@require('owner', 'admin')
@limiter.limit('10 per hour')
def subscribe():
    if not billing.enabled():
        raise APIError('Cobrança desativada.', 404)
    workspace = db.session.get(Workspace, g.workspace_id)
    data = payload(SubscribeSchema)
    row = billing.subscribe(workspace, g.user, data['cpf_cnpj'])
    audit('billing.subscribe', row)
    db.session.commit()
    return billing.status_payload(workspace), 201


@bp.post('/billing/asaas/webhook')
@limiter.limit('300 per minute')
def asaas_webhook():
    if not billing.check_webhook_token(request.headers.get('asaas-access-token')):
        current_app.logger.warning('asaas_webhook_auth_failed')
        raise APIError('Autenticação de webhook inválida.', 401)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError('Payload inválido.')
    return {'result': billing.apply_event(body)}
