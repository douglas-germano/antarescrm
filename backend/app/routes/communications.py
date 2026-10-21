import hashlib
import hmac
import re
import time

from flask import Blueprint, g, request
from marshmallow import fields as f
from marshmallow import validate

from ..common import APIError, add, commit, get, page, payload, query, require, update
from ..extensions import db, limiter
from ..models import (
    AuditLog,
    Contact,
    InboxMessage,
    InboxThread,
    MessageTemplate,
    WhatsAppConversation,
    WhatsAppMessage,
    Workspace,
    now,
)
from ..schemas import StrictSchema, choice, ref, text
from ..services.automations import received_reply
from ..services.communications import account_config, available, dispatch, enqueue, render
from ..services.instagram import send_reply
from .whatsapp import message_send

bp = Blueprint('communications', __name__)


class TemplateSchema(StrictSchema):
    name = text(150, required=True)
    channel = choice('email sms whatsapp', required=True)
    subject = f.String(validate=validate.Length(max=180), load_default='')
    content = text(20000, required=True)


class SendSchema(StrictSchema):
    contact_ids = f.List(ref(required=True), required=True, validate=validate.Length(min=1, max=100))
    template_id = ref(required=True)
    idempotency_key = ref(required=True)


class ReceiveSchema(StrictSchema):
    provider_id = text(100, required=True)
    address = text(254, required=True)
    content = text(20000, required=True)
    subject = f.String(validate=validate.Length(max=180), load_default='')


class ReplySchema(StrictSchema):
    content = text(20000, required=True)
    idempotency_key = ref(required=True)


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
    template = get(MessageTemplate, data['template_id'])
    contacts = [get(Contact, identifier) for identifier in dict.fromkeys(data['contact_ids'])]
    if not available(g.workspace_id, template.channel):
        raise APIError('Configure o canal no servidor antes de criar o disparo.', 503)
    messages = [
        enqueue(
            g.workspace_id,
            contact,
            template.channel,
            render(template.content, contact),
            render(template.subject, contact),
            data['idempotency_key'] + ':' + contact.id,
            g.user.id,
        )
        for contact in contacts
    ]
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
    items = []
    for thread in query(InboxThread).order_by(InboxThread.updated_at.desc()).limit(200):
        last = query(InboxMessage).filter_by(thread_id=thread.id).order_by(InboxMessage.created_at.desc()).first()
        items.append(
            {
                **thread.to_dict(),
                'source': 'inbox',
                'preview': last.content[:255] if last else '',
                'last_status': last.status if last else '',
            }
        )
        if thread.channel == 'instagram':
            owner = db.session.get(Contact, thread.contact_id) if thread.contact_id else None
            username = (owner.custom_fields or {}).get('instagram_username') if owner else None
            items[-1]['display_address'] = '@' + username if username else 'Instagram'
    for thread in query(WhatsAppConversation).order_by(WhatsAppConversation.last_message_at.desc()).limit(200):
        items.append(
            {
                **thread.to_dict(),
                'source': 'whatsapp',
                'channel': 'whatsapp',
                'address': thread.phone,
                'preview': thread.last_message_preview or '',
            }
        )
    items.sort(key=lambda row: row.get('last_message_at') or row.get('updated_at') or '', reverse=True)
    return {'items': items}


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


@bp.post('/inbox/<source>/<uuid:thread_id>/messages')
@require()
@limiter.limit('30 per minute')
def reply(source, thread_id):
    if source == 'whatsapp':
        return message_send(thread_id)
    if source != 'inbox':
        raise APIError('Conversa não encontrada.', 404)
    thread = get(InboxThread, thread_id)
    data = payload(ReplySchema)
    if thread.channel == 'instagram':
        row = send_reply(thread, data['content'], data['idempotency_key'], g.user.id)
        return row.to_dict(), 200
    if not thread.contact_id:
        raise APIError('Cadastre este remetente como contato antes de responder.', 422)
    contact = get(Contact, thread.contact_id)
    if not available(g.workspace_id, thread.channel):
        raise APIError('Configure o canal no servidor antes de responder.', 503)
    row = enqueue(
        g.workspace_id, contact, thread.channel, data['content'], thread.subject, data['idempotency_key'], g.user.id
    )
    return commit(row, 202)


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
    address = data['address'].strip().lower()
    if channel == 'email':
        f.Email().deserialize(address)
    else:
        if not re.fullmatch(r'\+\d{8,15}', address):
            raise APIError('Telefone inválido.', 422)
    key = 'receive:' + channel + ':' + data['provider_id']
    existing = InboxMessage.query.filter_by(workspace_id=workspace_id, idempotency_key=key).first()
    if existing:
        return {'received': True}
    field = Contact.email if channel == 'email' else Contact.phone
    contact = Contact.query.filter(
        Contact.workspace_id == workspace_id, field == address, Contact.archived.is_(False)
    ).first()
    thread = InboxThread.query.filter_by(workspace_id=workspace_id, channel=channel, address=address).first()
    if not thread:
        thread = InboxThread(
            workspace_id=workspace_id,
            channel=channel,
            address=address,
            contact_id=contact.id if contact else None,
            subject=data['subject'],
        )
        db.session.add(thread)
        db.session.flush()
    elif contact and not thread.contact_id:
        thread.contact_id = contact.id
    thread.updated_at = now()
    row = InboxMessage(
        workspace_id=workspace_id,
        thread_id=thread.id,
        direction='in',
        content=data['content'],
        subject=data['subject'],
        status='received',
        idempotency_key=key,
        provider_id=data['provider_id'],
    )
    db.session.add(row)
    db.session.flush()
    if contact:
        received_reply(workspace_id, contact, row.id)
    db.session.add(
        AuditLog(
            workspace_id=workspace_id,
            action='receive_message',
            resource='inbox_messages',
            resource_id=row.id,
            details={'channel': channel},
        )
    )
    db.session.commit()
    return {'received': True}, 201
