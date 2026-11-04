"""Shared HTTP parsing for WhatsApp endpoints; delivery belongs to the messaging service."""

from flask import request

from ..common import APIError, current_account, payload
from ..schemas.communications import WhatsAppSendSchema
from ..services import messaging


def send_whatsapp_request(conversation_id):
    account = current_account()
    conversation = messaging.whatsapp_target(account, conversation_id)
    file = None
    if request.mimetype == 'multipart/form-data':
        file = request.files.get('file')
        content = request.form.get('content', '').strip()
        key = request.form.get('idempotency_key', '')
        if not file or not key or len(key) > 100 or len(content) > 20000:
            raise APIError('Informe arquivo e chave de envio válidos.')
    else:
        data = payload(WhatsAppSendSchema)
        content, key = data['content'], data['idempotency_key']
    message, created = messaging.send_whatsapp(account, conversation, content, key, file)
    return message.to_dict(), 201 if created else 200
