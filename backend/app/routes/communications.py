import hashlib
import hmac
import re
import time

from flask import Blueprint, g, request
from marshmallow import fields as f
from marshmallow import validate

from ..common import APIError, add, audit, commit, get, page, payload, query, require, update, user_ref
from ..extensions import db, limiter
from ..models import (
    AuditLog,
    Contact,
    InboxMessage,
    InboxThread,
    MessageTemplate,
    Opportunity,
    WhatsAppConversation,
    WhatsAppMessage,
    Workspace,
    now,
)
from ..schemas import OpportunitySchema, StrictSchema, choice, ref, text
from ..services import inbox_opportunities, notifications
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


class InboxContactSchema(StrictSchema):
    name = text(required=True)
    email = f.Email(allow_none=True, validate=validate.Length(max=254))
    phone = text(30, allow_none=True)


class InboxOpportunitySchema(OpportunitySchema):
    idempotency_key = ref(required=True)
    contact = f.Nested(InboxContactSchema)


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
    """Every conversation across channels, newest first, with what the list needs to triage it."""
    items = []
    inbox_threads = query(InboxThread).order_by(InboxThread.updated_at.desc()).limit(200).all()
    last_in = (
        dict(
            db.session.query(InboxMessage.thread_id, db.func.max(InboxMessage.created_at))
            .filter(InboxMessage.thread_id.in_([t.id for t in inbox_threads]), InboxMessage.direction == 'in')
            .group_by(InboxMessage.thread_id)
            .all()
        )
        if inbox_threads
        else {}
    )
    for thread in inbox_threads:
        last = query(InboxMessage).filter_by(thread_id=thread.id).order_by(InboxMessage.created_at.desc()).first()
        items.append(
            {
                **thread.to_dict(),
                'source': 'inbox',
                'preview': last.content[:255] if last else '',
                'last_status': last.status if last else '',
                'last_direction': last.direction if last else '',
                'last_message_at': (last.created_at.isoformat() if last else None),
                'last_inbound_at': last_in[thread.id].isoformat() if last_in.get(thread.id) else None,
            }
        )
    last_direction = (
        db.session.query(WhatsAppMessage.direction)
        .filter(WhatsAppMessage.conversation_id == WhatsAppConversation.id)
        .order_by(WhatsAppMessage.occurred_at.desc())
        .limit(1)
        .correlate(WhatsAppConversation)
        .scalar_subquery()
    )
    for thread, direction in (
        query(WhatsAppConversation)
        .add_columns(last_direction)
        .order_by(WhatsAppConversation.last_message_at.desc())
        .limit(200)
    ):
        items.append(
            {
                **thread.to_dict(),
                'source': 'whatsapp',
                'channel': 'whatsapp',
                'address': thread.phone,
                'preview': thread.last_message_preview or '',
                'last_direction': direction or '',
            }
        )
    contact_ids = {item['contact_id'] for item in items if item.get('contact_id')}
    contacts = {c.id: c for c in query(Contact).filter(Contact.id.in_(contact_ids))} if contact_ids else {}
    open_deals = (
        {
            row[0]
            for row in query(Opportunity)
            .filter(Opportunity.contact_id.in_(contact_ids), Opportunity.status == 'open')
            .with_entities(Opportunity.contact_id)
        }
        if contact_ids
        else set()
    )
    counts = notifications.thread_counts()
    for item in items:
        contact = contacts.get(item.get('contact_id'))
        item['has_open_deal'] = item.get('contact_id') in open_deals
        if item['channel'] == 'instagram':
            username = (contact.custom_fields or {}).get('instagram_username') if contact else None
            item['display_address'] = '@' + username if username else 'Instagram'
        key = (item['source'], item['id'])
        if key in counts:
            item['unread_count'] = counts[key]
    items.sort(key=lambda row: row.get('last_message_at') or row.get('updated_at') or '', reverse=True)
    return {'items': items}


class ThreadUpdate(StrictSchema):
    status = choice('open closed')
    assigned_to_id = ref(nullable=True)


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


class NotificationReadSchema(StrictSchema):
    source = choice('whatsapp inbox', required=True)
    thread_id = ref(required=True)
    message_id = ref(required=True)


@bp.get('/inbox/notifications')
@require()
def notification_feed():
    return notifications.feed()


@bp.post('/inbox/notifications/read')
@require()
@limiter.limit('120 per minute')
def notification_read():
    data = payload(NotificationReadSchema)
    notifications.read_message(data['source'], data['thread_id'], data['message_id'])
    db.session.commit()
    return {'read': True}


@bp.post('/inbox/notifications/read-all')
@require()
@limiter.limit('30 per minute')
def notification_read_all():
    notifications.read_all()
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
    notifications.record(thread, row, 'inbox')
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
