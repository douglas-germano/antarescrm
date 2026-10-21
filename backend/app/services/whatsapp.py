"""Conversation persistence, idempotency and media recovery adapted from SDental."""
import base64
import binascii
import re
import secrets
from datetime import timedelta
from flask import current_app
from sqlalchemy.exc import IntegrityError
from ..extensions import db
from ..models import (WhatsAppConnection, WhatsAppConversation, WhatsAppMessage, WhatsAppMedia,
                      Contact, now)
from ..common import APIError
from ..utils.whatsapp_message import normalize_raw_message, MEDIA_PLACEHOLDER_TEXT
from .evolution import EvolutionService


def new(model_class, workspace_id, **values):
    row = model_class(workspace_id=workspace_id, **values)
    db.session.add(row)
    db.session.flush()
    return row


def connection_for(workspace_id):
    row = WhatsAppConnection.query.filter_by(workspace_id=workspace_id).first()
    if row:
        return row
    try:
        with db.session.begin_nested():
            row = new(WhatsAppConnection, workspace_id, instance_name='crm-' + workspace_id.replace('-', '')[:20],
                      webhook_secret=secrets.token_urlsafe(40))
        return row
    except IntegrityError:
        return WhatsAppConnection.query.filter_by(workspace_id=workspace_id).one()


def normalize_phone(value):
    digits = re.sub(r'\D', '', str(value))
    if len(digits) in (10, 11):
        digits = '55' + digits
    if not 10 <= len(digits) <= 15:
        raise APIError('Informe o telefone com DDI e DDD.')
    return digits


def phone_variants(digits):
    """The number plus its Brazilian mobile variant with/without the 9th digit."""
    digits = re.sub(r'\D', '', str(digits))
    variants = [digits]
    match = re.fullmatch(r'55(\d{2})(9?)(\d{8})', digits)
    if match:
        ddd, nine, rest = match.groups()
        variants.append(f'55{ddd}{rest}' if nine else f'55{ddd}9{rest}')
    return variants


def normalize_text(value):
    return ' '.join(str(value or '').split())


def conversation_for(connection, phone, name=None):
    phone = normalize_phone(phone)
    variants = phone_variants(phone)
    row = WhatsAppConversation.query.filter(WhatsAppConversation.workspace_id == connection.workspace_id,
                                            WhatsAppConversation.phone.in_(variants)).order_by(WhatsAppConversation.created_at).first()
    if row:
        return row
    try:
        with db.session.begin_nested():
            contacts = Contact.query.filter_by(workspace_id=connection.workspace_id, archived=False).all()
            accepted = set(phone_variants(phone)) | {v[2:] for v in phone_variants(phone) if v.startswith('55')}
            contact = next((c for c in contacts if c.phone and re.sub(r'\D', '', c.phone) in accepted), None)
            if not contact:
                contact = new(Contact, connection.workspace_id, name=(name or phone)[:180], phone=phone, source='WhatsApp')
                from .automations import emit
                emit(connection.workspace_id, 'contact.created', contact.id, contact)
            row = new(WhatsAppConversation, connection.workspace_id, phone=phone, contact_name=(name or contact.name)[:180],
                      contact_id=contact.id)
        return row
    except IntegrityError:
        return WhatsAppConversation.query.filter(WhatsAppConversation.workspace_id == connection.workspace_id,
                                                 WhatsAppConversation.phone.in_(variants)).order_by(WhatsAppConversation.created_at).first()


def ingest(connection, raw, historical=False):
    normalized = normalize_raw_message(raw)
    if not normalized or not normalized.get('evolution_id'):
        return None, False
    provider_id = str(normalized['evolution_id'])[:180]
    existing = WhatsAppMessage.query.filter_by(workspace_id=connection.workspace_id, provider_id=provider_id).first()
    if existing:
        return existing, False
    conversation = conversation_for(connection, normalized['phone'], raw.get('pushName'))
    conversation = WhatsAppConversation.query.filter_by(id=conversation.id).with_for_update().one()
    # Re-check after locking: retries may race between HTTP workers.
    existing = WhatsAppMessage.query.filter_by(workspace_id=connection.workspace_id, provider_id=provider_id).first()
    if existing:
        return existing, False
    outgoing = normalized['from_me']
    if outgoing and not historical:
        kind, content = normalized['message_type'], normalize_text(normalized['content'])
        candidates = WhatsAppMessage.query.filter_by(conversation_id=conversation.id, direction='out').filter(
            WhatsAppMessage.provider_id.is_(None), WhatsAppMessage.created_at >= now() - timedelta(minutes=3)
        ).order_by(WhatsAppMessage.created_at.desc()).all()

        def same(candidate):
            if candidate.kind != kind:
                return False
            if kind != 'text' and (not content or content == normalize_text(MEDIA_PLACEHOLDER_TEXT.get(kind, ''))):
                return True
            return normalize_text(candidate.content) == content
        pending = next((c for c in candidates if c.status in ('pending', 'unknown') and same(c)), None)
        if pending:
            pending.provider_id, pending.status = provider_id, 'sent'
            return pending, False
        sent_by_us = next((c for c in candidates if c.sent_via == 'platform' and c.kind == kind), None)
        if sent_by_us:
            # Our own message echoed back with altered text: attach it.
            sent_by_us.provider_id = provider_id
            if sent_by_us.status in ('pending', 'unknown'):
                sent_by_us.status = 'sent'
            return sent_by_us, False
    row = new(WhatsAppMessage, connection.workspace_id, conversation_id=conversation.id, provider_id=provider_id,
              direction='out' if outgoing else 'in', content=str(normalized['content'])[:20000],
              kind=normalized['message_type'], status='sent' if outgoing else 'received',
              occurred_at=normalized['timestamp'], raw_message={k: raw[k] for k in ('key', 'message', 'messageTimestamp') if k in raw},
              mimetype=normalized['media_mimetype'])
    # Preserve chronology when importing old records.
    timestamp = normalized['timestamp']
    previous = conversation.last_message_at
    if previous and previous.tzinfo is None:
        previous = previous.replace(tzinfo=timestamp.tzinfo)
    if not previous or timestamp >= previous:
        conversation.last_message_at = timestamp
        conversation.last_message_preview = row.content[:255]
    if not historical and not outgoing:
        conversation.unread_count += 1
        conversation.status = 'open'
        if conversation.contact_id:
            from .automations import received_reply
            received_reply(connection.workspace_id, db.session.get(Contact, conversation.contact_id), row.id)
    return row, True


def send_outgoing(connection, conversation, content, idempotency_key, user_id=None, file=None):
    from ..models import CommunicationSuppression
    if conversation.contact_id and CommunicationSuppression.query.filter_by(workspace_id=connection.workspace_id, contact_id=conversation.contact_id, channel='whatsapp').first():
        raise APIError('Contato não autoriza mensagens neste canal.', 409)
    conversation = WhatsAppConversation.query.filter_by(id=conversation.id, workspace_id=connection.workspace_id).with_for_update().one()
    existing = WhatsAppMessage.query.filter_by(workspace_id=connection.workspace_id, idempotency_key=idempotency_key).first()
    if existing:
        expected_content = content or MEDIA_PLACEHOLDER_TEXT.get(existing.kind, '')
        if existing.conversation_id != conversation.id or existing.content != expected_content:
            raise APIError('Chave de envio já utilizada em outra mensagem.', 409)
        if file:
            cached = WhatsAppMedia.query.filter_by(message_id=existing.id).first()
            retry_bytes = file.read(current_app.config['WHATSAPP_MEDIA_MAX_BYTES'] + 1)
            if not cached or retry_bytes != cached.content:
                raise APIError('Chave de envio já utilizada para outro arquivo.', 409)
        elif existing.kind != 'text':
            raise APIError('Esta chave pertence ao envio de um arquivo.', 409)
        return existing, False
    gateway = EvolutionService(connection)
    if connection.state != 'open':
        raise APIError('Conecte o WhatsApp antes de enviar mensagens.', 409)
    kind, mime, filename, data = 'text', None, None, None
    if file:
        data = file.read(current_app.config['WHATSAPP_MEDIA_MAX_BYTES'] + 1)
        if not data or len(data) > current_app.config['WHATSAPP_MEDIA_MAX_BYTES']:
            raise APIError('O arquivo deve ter entre 1 byte e 10 MB.')
        mime = file.mimetype or 'application/octet-stream'
        from werkzeug.utils import secure_filename
        filename = secure_filename(file.filename or 'arquivo')[:255] or 'arquivo'
        if mime.startswith('image/') and mime not in ('image/svg+xml', 'image/html'):
            kind = 'image'
        elif mime.startswith('audio/'):
            kind = 'audio'
        elif mime.startswith('video/'):
            kind = 'video'
        else:
            kind = 'document'
        if kind == 'audio' and content:
            raise APIError('Áudios não aceitam legenda. Envie o texto separadamente.')
    row = new(WhatsAppMessage, connection.workspace_id, conversation_id=conversation.id, direction='out',
              content=content or MEDIA_PLACEHOLDER_TEXT.get(kind, ''), kind=kind, status='pending', idempotency_key=idempotency_key,
              sent_by_id=user_id, sent_via='platform', mimetype=mime, filename=filename)
    if data:
        new(WhatsAppMedia, connection.workspace_id, message_id=row.id, content=data, mimetype=mime, filename=filename)
    if user_id and not conversation.assigned_to_id:
        conversation.assigned_to_id = user_id
    conversation.last_message_at, conversation.last_message_preview = now(), row.content[:255]
    db.session.commit()  # Durable outbox BEFORE network; ambiguous sends are not blindly retried.
    try:
        result = gateway.send_media(conversation.phone, kind, base64.b64encode(data).decode(), mime, filename, content) if data else gateway.send_text(conversation.phone, content)
        row = db.session.get(WhatsAppMessage, row.id)
        provider_id = (result.get('key') or {}).get('id') or result.get('id')
        if provider_id:
            row.provider_id = str(provider_id)[:180]
        if row.status not in ('delivered', 'read'):
            row.status = 'sent'
    except APIError as error:
        row = db.session.get(WhatsAppMessage, row.id)
        if row.status not in ('sent', 'delivered', 'read'):
            row.status = 'unknown'  # Gateway could have accepted despite losing its HTTP response.
            row.error = error.message
    db.session.commit()
    return row, True


def media_for(connection, message):
    cached = WhatsAppMedia.query.filter_by(message_id=message.id, workspace_id=connection.workspace_id).first()
    if cached:
        return cached
    if message.kind == 'text' or not message.provider_id:
        raise APIError('Mídia não disponível.', 404)
    response = EvolutionService(connection).media(message)
    encoded = response.get('base64') or response.get('media')
    if not isinstance(encoded, str):
        raise APIError('A mídia não está disponível na Evolution API.', 404)
    if len(encoded) > current_app.config['WHATSAPP_MEDIA_MAX_BYTES'] * 1.5:
        raise APIError('Mídia superior ao limite de 10 MB.', 413)
    try:
        content = base64.b64decode(encoded.split(',', 1)[-1], validate=True)
    except (binascii.Error, ValueError):
        raise APIError('A Evolution retornou uma mídia inválida.', 502)
    if not content or len(content) > current_app.config['WHATSAPP_MEDIA_MAX_BYTES']:
        raise APIError('Mídia vazia ou superior a 10 MB.', 413)
    mime = str(response.get('mimetype') or message.mimetype or 'application/octet-stream')[:150]
    from werkzeug.utils import secure_filename
    filename = secure_filename(response.get('fileName') or response.get('filename') or message.filename or ('arquivo.' + mime.split('/')[-1]))[:255] or 'arquivo'
    try:
        with db.session.begin_nested():
            cached = new(WhatsAppMedia, connection.workspace_id, message_id=message.id, content=content, mimetype=mime, filename=filename)
        db.session.commit()
        return cached
    except IntegrityError:
        return WhatsAppMedia.query.filter_by(message_id=message.id).one()
