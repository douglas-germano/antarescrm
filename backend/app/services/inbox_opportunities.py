"""Create a CRM deal and link its contact without leaving a conversation."""

import hashlib
import json

from flask import g

from ..common import APIError, add, audit, get, query
from ..models import AuditLog, Contact, Opportunity
from . import opportunities
from .automations import emit


def create(thread, source, data):
    identifier = data.pop('idempotency_key')
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    previous = query(Opportunity).filter_by(id=identifier).first()
    receipt = query(AuditLog).filter_by(action='inbox_create_opportunity', resource_id=identifier).first()
    if previous or receipt:
        details = receipt.details if receipt else {}
        if (
            not previous
            or details.get('source') != source
            or details.get('thread_id') != thread.id
            or details.get('request_hash') != digest
        ):
            raise APIError('Esta solicitação já foi usada. Confira o negócio criado antes de tentar novamente.', 409)
        return previous, 200

    new_contact = data.pop('contact', None)
    contact_id = data.get('contact_id')
    if new_contact and (contact_id or thread.contact_id):
        raise APIError('Use o contato vinculado ou selecione apenas uma forma de cadastro.', 422)
    if thread.contact_id and contact_id and thread.contact_id != contact_id:
        raise APIError('O contato da conversa mudou. Reabra o formulário para criar o negócio.', 409)
    contact_id = thread.contact_id or contact_id
    if not contact_id and not new_contact:
        raise APIError('Selecione um contato ou cadastre-o nesta conversa.', 422)

    # Validate account-scoped references before creating a new contact or changing the thread.
    opportunities.validate({**data, 'contact_id': contact_id})
    if new_contact:
        channel = 'whatsapp' if source == 'whatsapp' else thread.channel
        contact = add(
            Contact,
            {
                **new_contact,
                'source': {'whatsapp': 'WhatsApp', 'instagram': 'Instagram', 'email': 'E-mail', 'sms': 'SMS'}.get(
                    channel, channel
                ),
                'owner_id': data.get('owner_id') or g.user.id,
            },
        )
        emit(g.workspace_id, 'contact.created', contact.id, contact)
    else:
        contact = get(Contact, contact_id)

    data['contact_id'] = contact.id
    row = opportunities.create({**data, 'id': identifier}, g.user.id)
    if not thread.contact_id:
        thread.contact_id = contact.id
        if source == 'whatsapp' and not thread.contact_name:
            thread.contact_name = contact.name
        audit('inbox_link_contact', thread, {'contact_id': contact.id})
    audit('inbox_create_opportunity', row, {'source': source, 'thread_id': thread.id, 'request_hash': digest})
    return row, 201
