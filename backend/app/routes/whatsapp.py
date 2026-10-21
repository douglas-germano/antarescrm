import hmac
import hashlib
from datetime import timedelta, timezone
from flask import Blueprint, request, current_app, g, send_file
from io import BytesIO
from ..extensions import db, limiter
from ..models import WhatsAppConnection, WhatsAppConversation, WhatsAppMessage, Contact, now
from ..schemas import StrictSchema, text, choice, ref
from ..common import require, APIError, payload, query, get, page, user_ref, audit
from ..services.whatsapp import connection_for, conversation_for, ingest, send_outgoing, media_for, normalize_phone
from ..services.evolution import EvolutionService

bp = Blueprint('whatsapp', __name__)


class ConversationCreate(StrictSchema):
    phone = text(30, required=True)
    contact_name = text(180, allow_none=True)
    contact_id = ref(nullable=True)


class ConversationUpdate(StrictSchema):
    status = choice('open closed')
    assigned_to_id = ref(nullable=True)
    contact_id = ref(nullable=True)
    contact_name = text(180)


class SendSchema(StrictSchema):
    content = text(20000, required=True)
    idempotency_key = text(100, required=True)


def connection_info(connection):
    config = current_app.config
    missing = [key for key in ('EVOLUTION_API_URL', 'EVOLUTION_API_KEY', 'WHATSAPP_WEBHOOK_BASE_URL') if not config.get(key)]
    return {**connection.to_dict(), 'configured': not missing, 'missing_variables': missing,
            'connected': connection.state == 'open'}


@bp.get('/whatsapp/connection')
@require()
def connection():
    row = connection_for(g.workspace_id)
    db.session.commit()
    if request.args.get('refresh') == 'true' and current_app.config.get('EVOLUTION_API_URL') and current_app.config.get('EVOLUTION_API_KEY'):
        result = EvolutionService(row).status()
        row.state = result['state']
        if result.get('phone_number'):
            row.phone_number = result['phone_number']
        db.session.commit()
    return connection_info(row)


@bp.post('/whatsapp/connection/connect')
@require('owner', 'admin')
def connect():
    row = connection_for(g.workspace_id)
    db.session.commit()
    EvolutionService(row).create_instance()
    row.webhook_configured = True
    db.session.commit()
    result = EvolutionService(row).status()
    row.state = result['state']
    db.session.commit()
    return {**connection_info(row), **({} if result['connected'] else EvolutionService(row).qr())}


@bp.get('/whatsapp/connection/qr')
@require('owner', 'admin')
@limiter.limit('10 per minute')
def qr():
    row = connection_for(g.workspace_id)
    result = EvolutionService(row).qr()
    db.session.commit()
    return result


@bp.post('/whatsapp/connection/disconnect')
@require('owner', 'admin')
def disconnect():
    row = connection_for(g.workspace_id)
    EvolutionService(row).disconnect()
    row.state = 'disconnected'
    audit('disconnect', row)
    db.session.commit()
    return connection_info(row)


@bp.get('/whatsapp/conversations')
@require()
def conversations():
    q = query(WhatsAppConversation)
    for key in ('status', 'contact_id', 'assigned_to_id'):
        if request.args.get(key):
            q = q.filter(getattr(WhatsAppConversation, key) == request.args[key])
    if request.args.get('search'):
        term = '%' + request.args['search'] + '%'
        q = q.filter(db.or_(WhatsAppConversation.phone.ilike(term), WhatsAppConversation.contact_name.ilike(term)))
    return page(q.order_by(WhatsAppConversation.last_message_at.desc().nullslast(), WhatsAppConversation.created_at.desc()))


@bp.post('/whatsapp/conversations')
@require()
def conversation_create():
    data = payload(ConversationCreate)
    if data.get('contact_id'):
        get(Contact, data['contact_id'])
    row = conversation_for(connection_for(g.workspace_id), data['phone'], data.get('contact_name'))
    if data.get('contact_id'):
        row.contact_id = data['contact_id']
    db.session.commit()
    return row.to_dict(), 201


@bp.patch('/whatsapp/conversations/<uuid:conversation_id>')
@require()
def conversation_update(conversation_id):
    row = get(WhatsAppConversation, conversation_id, lock=True)
    data = payload(ConversationUpdate)
    user_ref(data.get('assigned_to_id'))
    if data.get('contact_id'):
        get(Contact, data['contact_id'])
    for key, value in data.items():
        setattr(row, key, value)
    audit('conversation_update', row)
    db.session.commit()
    return row.to_dict()


@bp.post('/whatsapp/conversations/<uuid:conversation_id>/read')
@require()
def mark_read(conversation_id):
    row = get(WhatsAppConversation, conversation_id, lock=True)
    row.unread_count = 0
    db.session.commit()
    return row.to_dict()


@bp.get('/whatsapp/conversations/<uuid:conversation_id>/messages')
@require()
def messages(conversation_id):
    row = get(WhatsAppConversation, conversation_id)
    return page(query(WhatsAppMessage).filter_by(conversation_id=row.id).order_by(WhatsAppMessage.occurred_at.desc(), WhatsAppMessage.created_at.desc()))


@bp.post('/whatsapp/conversations/<uuid:conversation_id>/messages')
@require()
@limiter.limit('30 per minute')
def message_send(conversation_id):
    row = get(WhatsAppConversation, conversation_id)
    if row.status == 'closed':
        raise APIError('Reabra a conversa antes de enviar.', 409)
    file = None
    if request.mimetype == 'multipart/form-data':
        file = request.files.get('file')
        content = request.form.get('content', '').strip()
        key = request.form.get('idempotency_key', '')
        if not file or not key or len(key) > 100 or len(content) > 20000:
            raise APIError('Informe arquivo e chave de envio válidos.')
    else:
        data = payload(SendSchema)
        content, key = data['content'], data['idempotency_key']
    message, created = send_outgoing(connection_for(g.workspace_id), row, content, key, g.user.id, file)
    return message.to_dict(), 201 if created else 200


@bp.get('/whatsapp/messages/<uuid:message_id>/media')
@require()
def media(message_id):
    message = get(WhatsAppMessage, message_id)
    asset = media_for(connection_for(g.workspace_id), message)
    base_mime = asset.mimetype.split(';')[0].strip().lower()
    safe_inline = base_mime in ('image/png', 'image/jpeg', 'image/webp', 'image/gif', 'audio/ogg', 'audio/mpeg', 'audio/mp4', 'video/mp4', 'video/webm')
    return send_file(BytesIO(asset.content), mimetype=base_mime if safe_inline else 'application/octet-stream',
                     download_name=asset.filename, as_attachment=not safe_inline, conditional=True)


@bp.post('/whatsapp/conversations/<uuid:conversation_id>/sync')
@require()
@limiter.limit('5 per minute')
def sync_history(conversation_id):
    row = get(WhatsAppConversation, conversation_id)
    connection = connection_for(g.workspace_id)
    raw_rows = EvolutionService(connection).history(row.phone)
    count = 0
    for raw in raw_rows:
        from ..utils.whatsapp_message import normalize_raw_message
        normalized = normalize_raw_message(raw)
        if normalized and normalize_phone(normalized['phone']) == row.phone:
            _, added = ingest(connection, raw, historical=True)
            count += int(added)
    db.session.commit()
    return {'imported': count, 'limit': 500}


def safe_equal(a, b):
    """Constant-time comparison that never raises (non-ASCII or non-str input is simply unequal)."""
    if not isinstance(a, (str, bytes)) or not isinstance(b, (str, bytes)):
        return False
    try:
        a = a.encode('utf-8') if isinstance(a, str) else a
        b = b.encode('utf-8') if isinstance(b, str) else b
        return hmac.compare_digest(a, b)
    except Exception:
        return False


def webhook_instance_key():
    body = request.get_json(silent=True)
    instance = body.get('instance') if isinstance(body, dict) else None
    if isinstance(instance, str) and 0 < len(instance) <= 80:
        return 'wa-instance:' + instance
    return request.remote_addr or 'unknown'


@bp.post('/whatsapp/webhook')
@bp.post('/whatsapp/webhook/<event_suffix>')
@limiter.limit('6000 per minute')
@limiter.limit('600 per minute', key_func=webhook_instance_key)
def webhook(event_suffix=None):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError('Payload inválido.')
    instance = body.get('instance')
    if not isinstance(instance, str):
        raise APIError('Instância obrigatória.')
    connection = WhatsAppConnection.query.filter_by(instance_name=instance).first()
    if not connection:
        current_app.logger.warning('whatsapp_webhook_auth_failed connection_id=unknown')
        raise APIError('Autenticação de webhook inválida.', 401)
    secret = request.headers.get('X-Webhook-Secret', '')
    signature = request.headers.get('X-Webhook-Signature', '').removeprefix('sha256=')
    connection_secret = connection.webhook_secret or ''
    expected = hmac.new(connection_secret.encode(), request.get_data(), hashlib.sha256).hexdigest()
    secret_valid = safe_equal(secret, connection_secret)
    signature_valid = safe_equal(signature, expected)
    valid = bool(connection_secret) and ((bool(secret) and secret_valid) or (bool(signature) and signature_valid))
    if not valid:
        current_app.logger.warning('whatsapp_webhook_auth_failed connection_id=%s workspace_id=%s', connection.id, connection.workspace_id)
        raise APIError('Autenticação de webhook inválida.', 401)
    connection.last_webhook_at = now()
    event = str(body.get('event', event_suffix or '')).lower().replace('_', '.')
    data = body.get('data') or {}
    if event == 'connection.update' and isinstance(data, dict):
        connection.state = str(data.get('state', 'unknown'))[:30]
    elif event == 'messages.upsert':
        rows = data if isinstance(data, list) else [data]
        if len(rows) > 200:
            raise APIError('Lote de mensagens superior ao limite.', 413)
        for raw in rows:
            if isinstance(raw, dict):
                ingest(connection, raw)
    elif event == 'messages.update':
        mapping = {'PENDING': 'sent', 'SERVER_ACK': 'sent', 'DELIVERY_ACK': 'delivered', 'READ': 'read', 'PLAYED': 'read', '1': 'sent', '2': 'sent', '3': 'delivered', '4': 'read', '5': 'read'}
        rank = {'unknown': 0, 'pending': 0, 'sent': 1, 'delivered': 2, 'read': 3}
        for update in data if isinstance(data, list) else [data]:
            if not isinstance(update, dict):
                continue
            provider_id = (update.get('key') or {}).get('id') or update.get('keyId') or update.get('id')
            status = mapping.get(str(update.get('status') or (update.get('update') or {}).get('status')))
            message = WhatsAppMessage.query.filter_by(workspace_id=connection.workspace_id, provider_id=provider_id, direction='out').first() if provider_id else None
            if message and status and rank.get(status, 0) > rank.get(message.status, 0):
                message.status = status
    db.session.commit()
    return {'status': 'received'}
