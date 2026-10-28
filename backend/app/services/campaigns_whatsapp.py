"""Reviewed WhatsApp campaigns using the existing durable, idempotent outbox."""

from collections import Counter
from contextlib import suppress

from ..common import APIError
from ..extensions import db
from ..models import CampaignRecipient, CommunicationSuppression, Contact, InboxMessage, WhatsAppConnection, now
from . import communications

MAX_RECIPIENTS = 100


def audience(workspace_id, filters):
    contacts = Contact.query.filter_by(workspace_id=workspace_id, archived=False).order_by(Contact.id).all()
    blocked_ids = {
        item.contact_id
        for item in CommunicationSuppression.query.filter_by(workspace_id=workspace_id, channel='whatsapp')
    }
    blocked_phones = set()
    for contact in Contact.query.filter(Contact.workspace_id == workspace_id, Contact.id.in_(blocked_ids)):
        with suppress(APIError):
            blocked_phones.add(communications.address_for(contact, 'whatsapp'))
    rows, seen = [], set()
    counts = {'without_phone': 0, 'invalid': 0, 'suppressed': 0, 'duplicates': 0}
    for contact in contacts:
        if filters.get('source') and contact.source != filters['source']:
            continue
        if filters.get('tag') and filters['tag'] not in (contact.tags or []):
            continue
        if not contact.phone:
            counts['without_phone'] += 1
            continue
        try:
            phone = communications.address_for(contact, 'whatsapp')
        except APIError:
            counts['invalid'] += 1
            continue
        if contact.id in blocked_ids or phone in blocked_phones:
            counts['suppressed'] += 1
        elif phone in seen:
            counts['duplicates'] += 1
        else:
            seen.add(phone)
            rows.append({'contact_id': contact.id, 'phone': phone, 'name': contact.name})
    return rows, counts


def connection(row):
    item = WhatsAppConnection.query.filter_by(workspace_id=row.workspace_id, state='open').first()
    if not item or (row.whatsapp_connection_id and row.whatsapp_connection_id != item.id):
        raise APIError('Conecte o WhatsApp desta conta antes de preparar ou enviar a campanha.', 409)
    return item


def prepare(row):
    if row.status != 'draft':
        return row
    from .campaigns import fingerprint

    item = connection(row)
    rows, _ = audience(row.workspace_id, row.audience)
    if not 1 <= len(rows) <= MAX_RECIPIENTS:
        raise APIError(f'Selecione de 1 a {MAX_RECIPIENTS} telefones válidos. Use tags ou origem para segmentar.', 422)
    row.whatsapp_connection_id = item.id
    row.audience_hash, row.recipient_count, row.status = fingerprint(rows), len(rows), 'ready'
    for contact in rows:
        db.session.add(
            CampaignRecipient(
                workspace_id=row.workspace_id,
                campaign_id=row.id,
                contact_id=contact['contact_id'],
                phone=contact['phone'],
            )
        )
    db.session.flush()
    return row


def send(row, audience_hash, user_id):
    from .campaigns import fingerprint

    if row.status in ('sending', 'sent', 'unknown', 'completed_with_issues'):
        return row
    if row.status != 'ready':
        raise APIError('Prepare e revise a campanha antes de enviar.', 409)
    connection(row)
    rows, _ = audience(row.workspace_id, row.audience)
    recipients = CampaignRecipient.query.filter_by(workspace_id=row.workspace_id, campaign_id=row.id).all()
    if (
        audience_hash != row.audience_hash
        or fingerprint(rows) != row.audience_hash
        or {(r['contact_id'], r['phone']) for r in rows} != {(r.contact_id, r.phone) for r in recipients}
    ):
        raise APIError('O público mudou. Crie um novo rascunho e revise os destinatários.', 409)
    for recipient in recipients:
        contact = db.session.get(Contact, recipient.contact_id)
        message = communications.enqueue(
            row.workspace_id,
            contact,
            'whatsapp',
            communications.render(row.content, contact),
            '',
            'campaign:' + row.id + ':' + contact.id,
            user_id,
        )
        recipient.message_id = message.id
    row.status, row.sent_at = 'sending', now()
    # Queue and campaign claim commit atomically in the route. No provider calls until process().
    return row


def progress(row):
    recipients = CampaignRecipient.query.filter_by(workspace_id=row.workspace_id, campaign_id=row.id).all()
    messages = {
        m.id: m
        for m in InboxMessage.query.filter(
            InboxMessage.workspace_id == row.workspace_id,
            InboxMessage.id.in_([r.message_id for r in recipients if r.message_id]),
        ).all()
    }
    counts = Counter(messages[r.message_id].status if r.message_id in messages else r.status for r in recipients)
    metrics = {key: counts[key] for key in ('prepared', 'queued', 'sending', 'sent', 'unknown', 'blocked', 'cancelled')}
    status = row.status
    if row.sent_at:
        if counts['queued'] or counts['sending']:
            status = 'sending'
        elif counts['unknown']:
            status = 'unknown'
        elif counts['blocked'] or counts['cancelled']:
            status = 'completed_with_issues'
        else:
            status = 'sent'
    return status, metrics


def process(row):
    if not row.sent_at:
        raise APIError('Confirme o envio da campanha primeiro.', 409)
    connection(row)
    ids = [
        r.message_id
        for r in CampaignRecipient.query.filter_by(workspace_id=row.workspace_id, campaign_id=row.id)
        if r.message_id
    ]
    # One provider operation per HTTP request; never drain unrelated messages.
    communications.dispatch(row.workspace_id, limit=1, message_ids=ids)
    row.status, _ = progress(row)
    db.session.commit()
    return row
