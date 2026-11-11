import hmac

from flask import Blueprint, g, request
from marshmallow import fields as f
from marshmallow import validate

from ..common import APIError, add, audit, commit, get, page, payload, query, require
from ..extensions import db, limiter
from ..models import BrevoConnection, EmailCampaign
from ..schemas import StrictSchema, choice, text
from ..services import brevo as service
from ..services import campaigns, campaigns_whatsapp

bp = Blueprint('brevo', __name__)


class ConnectionSchema(StrictSchema):
    api_key = f.String(load_only=True, validate=validate.Length(min=20, max=500))
    sender_email = f.Email(required=True, validate=validate.Length(max=254))
    sender_name = text(150, required=True)


class AudienceSchema(StrictSchema):
    tag = f.String(load_default='', validate=validate.Length(max=80))
    source = f.String(load_default='', validate=validate.Length(max=100))


class CampaignSchema(StrictSchema):
    channel = choice('email whatsapp', load_default='email')
    name = text(150, required=True)
    subject = f.String(load_default='', validate=validate.Length(max=180))
    content = text(20000, required=True)
    audience = f.Nested(AudienceSchema, load_default=dict)


class AudienceRequestSchema(AudienceSchema):
    channel = choice('email whatsapp', load_default='email')


def validate_campaign(data):
    if data.get('channel', 'email') == 'email' and not str(data.get('subject') or '').strip():
        raise APIError('Informe o assunto do e-mail.', 422)


class SendSchema(StrictSchema):
    audience_hash = f.String(required=True, validate=validate.Regexp(r'^[a-f0-9]{64}$'))
    consent_confirmed = f.Boolean(required=True, validate=validate.Equal(True))


@bp.get('/brevo/connection')
@require('owner', 'admin')
def connection():
    row = query(BrevoConnection).first()
    return {'connection': row.to_dict() if row else None}


@bp.post('/brevo/connection')
@require('owner', 'admin')
@limiter.limit('10 per minute')
def connect():
    row = service.connect(g.workspace_id, payload(ConnectionSchema))
    audit('brevo_connect', row)
    return commit(row)


@bp.delete('/brevo/connection')
@require('owner', 'admin')
def disconnect():
    row = query(BrevoConnection).with_for_update().first()
    if row:
        if (
            query(EmailCampaign)
            .filter_by(channel='email')
            .filter(EmailCampaign.status.in_(('preparing', 'importing', 'sending')))
            .first()
        ):
            raise APIError('Consulte a campanha em andamento antes de desconectar.', 409)
        row.active, row.encrypted_key = False, ''
        row.version += 1
        row.folder_id, row.webhook_id = None, None
        audit('brevo_disconnect', row)
        db.session.commit()
    return '', 204


@bp.post('/brevo/webhooks')
@require('owner', 'admin')
@limiter.limit('5 per minute')
def setup():
    row = query(BrevoConnection).filter_by(active=True).with_for_update().first()
    if not row:
        raise APIError('Conecte o Brevo primeiro.', 409)
    service.setup_webhook(row)
    audit('brevo_webhook_setup', row)
    return commit(row)


@bp.get('/campaigns')
@require('owner', 'admin')
def listing():
    rows = query(EmailCampaign).filter_by(archived=request.args.get('archived') == 'true')
    return page(rows.order_by(EmailCampaign.created_at.desc()), campaigns.serialize)


@bp.post('/campaigns/audience')
@require('owner', 'admin')
def audience():
    data = payload(AudienceRequestSchema)
    channel = data.pop('channel')
    rows, counts = campaigns.audience(g.workspace_id, data, channel)
    return {
        'total': len(rows),
        'excluded': counts,
        'sample': rows[:20],
        'limit': campaigns_whatsapp.MAX_RECIPIENTS if channel == 'whatsapp' else campaigns.MAX_RECIPIENTS,
    }


@bp.post('/campaigns')
@require('owner', 'admin')
def create():
    data = payload(CampaignSchema)
    validate_campaign(data)
    return commit(add(EmailCampaign, data), 201, campaigns.serialize)


@bp.patch('/campaigns/<uuid:identifier>')
@require('owner', 'admin')
def edit(identifier):
    row = get(EmailCampaign, identifier, lock=True)
    if row.status != 'draft' or row.archived:
        raise APIError('Somente rascunhos locais podem ser editados.', 409)
    data = payload(CampaignSchema, partial=True)
    if data.get('channel', row.channel) != row.channel:
        raise APIError('Crie uma nova campanha para mudar o canal.', 409)
    validate_campaign({'channel': row.channel, 'subject': data.get('subject', row.subject)})
    for key, value in data.items():
        setattr(row, key, value)
    audit('campaign_edit', row)
    return commit(row, serializer=campaigns.serialize)


@bp.delete('/campaigns/<uuid:identifier>')
@require('owner', 'admin')
def delete_campaign(identifier):
    row = get(EmailCampaign, identifier, lock=True)
    if row.status != 'draft':
        raise APIError('Somente rascunhos locais podem ser apagados.', 409)
    audit('campaign_delete', row)
    db.session.delete(row)
    db.session.commit()
    return '', 204


@bp.post('/campaigns/<uuid:identifier>/<action>')
@require('owner', 'admin')
@limiter.limit(lambda: '120 per minute' if request.view_args.get('action') == 'process' else '15 per minute')
def action(identifier, action):
    if action not in ('prepare', 'refresh', 'send', 'process', 'archive'):
        raise APIError('Ação indisponível.', 404)
    row = get(EmailCampaign, identifier, lock=True)
    if action == 'archive':
        if not row.archived:
            status = campaigns_whatsapp.progress(row)[0] if row.channel == 'whatsapp' else row.status
            if status in ('preparing', 'importing', 'sending'):
                raise APIError('Aguarde a conclusão do processamento para arquivar a campanha.', 409)
            row.archived = True
            audit('campaign_archive', row)
        return commit(row, serializer=campaigns.serialize)
    if row.archived and action != 'refresh':
        raise APIError('A campanha está arquivada.', 409)
    if action == 'send':
        data = payload(SendSchema)
        audit('campaign_send_requested', row, {'consent_confirmed': True})
        campaigns.send(row, data['audience_hash'], g.user.id)
    elif action == 'process':
        if row.channel != 'whatsapp':
            raise APIError('Ação indisponível para este canal.', 409)
        campaigns_whatsapp.process(row)
    elif action == 'prepare':
        campaigns.prepare(row)
    else:
        campaigns.refresh(row)
    return commit(row, serializer=campaigns.serialize)


@bp.post('/brevo/webhook/<uuid:identifier>')
@limiter.limit('600 per minute')
def webhook(identifier):
    row = BrevoConnection.query.filter_by(id=str(identifier), active=True).with_for_update().first()
    secret = request.headers.get('X-Brevo-Secret', '')
    if not row or not secret or not hmac.compare_digest(row.webhook_secret, secret):
        raise APIError('Evento não autorizado.', 401)
    body = request.get_json(silent=True)
    if not isinstance(body, (dict, list)) or (isinstance(body, list) and len(body) > 100):
        raise APIError('Evento inválido.', 422)
    for item in body if isinstance(body, list) else [body]:
        campaigns.receive(row, item)
    db.session.commit()
    return {'received': True}
