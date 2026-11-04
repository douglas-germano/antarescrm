import hashlib
import hmac
import time

from flask import Blueprint, g, request

from ..common import APIError, add, audit, commit, current_account, get, page, payload, query, require, update, user_ref
from ..extensions import db, limiter
from ..models import (
    Contact,
    InboxMessage,
    InboxThread,
    MessageTemplate,
    WhatsAppConversation,
    WhatsAppMessage,
    Workspace,
)
from ..schemas.communications import (
    InboxOpportunitySchema,
    NotificationReadSchema,
    ReceiveSchema,
    ReplySchema,
    SendSchema,
    TemplateSchema,
    ThreadUpdate,
)
from ..services import inbox as inbox_service
from ..services import inbox_opportunities, incoming, messaging, notifications
from ..services.communications import account_config, available, dispatch
from ._message_input import send_whatsapp_request

bp = Blueprint('communications', __name__)


@bp.get('/communications/channels')
@require()
def channels():
    return {
        'items': [
            {'channel': channel, 'configured': available(g.workspace_id, channel)}
            for channel in ('email', 'sms', 'whatsapp')
        ]
    }


@bp.get('/message-templates')
@require()
def templates():
    return page(query(MessageTemplate).order_by(MessageTemplate.name))


@bp.post('/message-templates')
@require('owner', 'admin')
def template_create():
    return commit(add(MessageTemplate, payload(TemplateSchema)), 201)


@bp.patch('/message-templates/<uuid:template_id>')
@require('owner', 'admin')
def template_update(template_id):
    row = get(MessageTemplate, template_id)
    update(row, payload(TemplateSchema, partial=True))
    return commit(row)


@bp.post('/communications/broadcasts')
@require('owner', 'admin')
@limiter.limit('10 per minute')
def broadcast():
    data = payload(SendSchema)
    messages = messaging.queue_broadcast(current_account(), data)
    db.session.commit()
    return {'items': [m.to_dict() for m in messages], 'total': len(messages)}, 202


@bp.post('/communications/dispatch')
@require('owner', 'admin')
@limiter.limit('5 per minute')
def dispatch_now():
    return {'items': dispatch(g.workspace_id, 20)}


@bp.post('/communications/messages/<uuid:message_id>/resume')
@require('owner', 'admin')
def resume(message_id):
    row = get(InboxMessage, message_id, lock=True)
    if row.status != 'blocked':
        raise APIError('Somente envios bloqueados por configuração podem ser retomados.', 409)
    thread = get(InboxThread, row.thread_id)
    if not available(g.workspace_id, thread.channel):
        raise APIError('O canal ainda não está configurado.', 503)
    update(row, {'status': 'queued', 'error': None})
    return commit(row)


@bp.get('/inbox')
@require()
def inbox():
    return inbox_service.list_threads(current_account())


@bp.patch('/inbox/inbox/<uuid:thread_id>')
@require()
def inbox_thread_update(thread_id):
    """Close, reopen or assign an Instagram or e-mail conversation, as WhatsApp ones already can be."""
    row = get(InboxThread, thread_id, lock=True)
    data = payload(ThreadUpdate)
    if data.get('assigned_to_id'):
        data['assigned_to_id'] = str(data['assigned_to_id'])
    user_ref(data.get('assigned_to_id'))
    for key, value in data.items():
        setattr(row, key, value)
    audit('conversation_update', row)
    db.session.commit()
    return {**row.to_dict(), 'source': 'inbox'}


@bp.get('/inbox/notifications')
@require()
def notification_feed():
    return notifications.feed(current_account())


@bp.post('/inbox/notifications/read')
@require()
@limiter.limit('120 per minute')
def notification_read():
    data = payload(NotificationReadSchema)
    notifications.read_message(current_account(), data['source'], data['thread_id'], data['message_id'])
    db.session.commit()
    return {'read': True}


@bp.post('/inbox/notifications/read-all')
@require()
@limiter.limit('30 per minute')
def notification_read_all():
    notifications.read_all(current_account())
    db.session.commit()
    return {'read': True}


@bp.get('/inbox/<source>/<uuid:thread_id>')
@require()
def inbox_thread(source, thread_id):
    if source not in ('whatsapp', 'inbox'):
        raise APIError('Conversa não encontrada.', 404)
    thread = get(WhatsAppConversation if source == 'whatsapp' else InboxThread, thread_id)
    contact = query(Contact).filter_by(id=thread.contact_id).first() if thread.contact_id else None
    return {
        **thread.to_dict(),
        'source': source,
        'channel': 'whatsapp' if source == 'whatsapp' else thread.channel,
        'address': thread.phone if source == 'whatsapp' else thread.address,
        'contact_name': contact.name if contact else getattr(thread, 'contact_name', None),
    }


@bp.get('/inbox/<source>/<uuid:thread_id>/messages')
@require()
def messages(source, thread_id):
    if source == 'whatsapp':
        thread = get(WhatsAppConversation, thread_id)
        return page(
            query(WhatsAppMessage).filter_by(conversation_id=thread.id).order_by(WhatsAppMessage.occurred_at.desc())
        )
    if source != 'inbox':
        raise APIError('Conversa não encontrada.', 404)
    thread = get(InboxThread, thread_id)
    return page(query(InboxMessage).filter_by(thread_id=thread.id).order_by(InboxMessage.created_at.desc()))


@bp.post('/inbox/<source>/<uuid:thread_id>/opportunities')
@require()
@limiter.limit('20 per minute')
def create_inbox_opportunity(source, thread_id):
    if source not in ('whatsapp', 'inbox'):
        raise APIError('Conversa não encontrada.', 404)
    data = payload(InboxOpportunitySchema)
    thread = get(WhatsAppConversation if source == 'whatsapp' else InboxThread, thread_id, lock=True)
    row, status = inbox_opportunities.create(thread, source, data)
    db.session.commit()
    return {'opportunity': row.to_dict(), 'conversation': thread.to_dict()}, status


@bp.post('/inbox/<source>/<uuid:thread_id>/messages')
@require()
@limiter.limit('30 per minute')
def reply(source, thread_id):
    if source == 'whatsapp':
        return send_whatsapp_request(thread_id)
    if source != 'inbox':
        raise APIError('Conversa não encontrada.', 404)
    row, status = messaging.send_inbox_reply(current_account(), thread_id, payload(ReplySchema))
    return row.to_dict(), status


@bp.post('/communications/receive/<uuid:workspace_id>/<channel>')
@limiter.limit('120 per minute')
def receive(workspace_id, channel):
    if channel not in ('email', 'sms'):
        raise APIError('Canal não encontrado.', 404)
    workspace_id = str(workspace_id)
    workspace = db.session.get(Workspace, workspace_id)
    config = account_config(workspace_id, channel)
    secret = config.get('inbound_secret')
    if not workspace or not workspace.active or not secret:
        raise APIError('Canal indisponível.', 404)
    timestamp = request.headers.get('X-Timestamp', '')
    raw = request.get_data()
    expected = hmac.new(secret.encode(), timestamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
    if (
        not timestamp.isdigit()
        or abs(time.time() - int(timestamp)) > 300
        or not hmac.compare_digest(expected, request.headers.get('X-Signature', ''))
    ):
        raise APIError('Assinatura inválida.', 401)
    data = payload(ReceiveSchema)
    created = incoming.receive_message(workspace_id, channel, data)
    if created:
        db.session.commit()
    return {'received': True}, 201 if created else 200
