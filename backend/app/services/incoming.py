"""Materialize signed inbound deliveries. Caller commits the message, notification and automation atomically."""

import re

from marshmallow import fields as f

from ..common import APIError
from ..extensions import db
from ..models import AuditLog, Contact, InboxMessage, InboxThread, now
from . import notifications
from .automations import received_reply


def receive_message(workspace_id, channel, data):
    address = data['address'].strip().lower()
    if channel == 'email':
        f.Email().deserialize(address)
    else:
        if not re.fullmatch(r'\+\d{8,15}', address):
            raise APIError('Telefone inválido.', 422)
    key = 'receive:' + channel + ':' + data['provider_id']
    existing = InboxMessage.query.filter_by(workspace_id=workspace_id, idempotency_key=key).first()
    if existing:
        return False
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
    return True
