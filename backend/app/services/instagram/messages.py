"""Instagram messages: message ingestion, echo reconciliation and payload formatting."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm.attributes import flag_modified

from ...common import APIError
from ...extensions import db
from ...models import Contact, InboxMessage, InboxThread, InstagramComment, InstagramEvent, Workspace, now
from . import client, profiles


def ingest_message(connection, item, key, historical=False):
    """Materialize inbound DMs and owner echoes; recording an echo never sends or starts an automation."""
    message = item.get('message') or {}
    mid = message.get('mid')
    if not mid or message.get('is_deleted'):
        return False
    sender = str((item.get('sender') or {}).get('id', ''))
    recipient = str((item.get('recipient') or {}).get('id', ''))
    outgoing = sender == connection.instagram_id
    if outgoing:
        peer = recipient
    else:
        if recipient != connection.instagram_id or message.get('is_echo'):
            return False
        peer = sender
    if not peer.isdigit() or peer == connection.instagram_id:
        return False
    content = message.get('text') or (
        ('[Anexo enviado no Instagram]' if outgoing else '[Anexo recebido no Instagram]')
        if message.get('attachments')
        else '[Mensagem do Instagram]'
    )
    try:
        occurred = datetime.fromtimestamp(float(item.get('timestamp')) / 1000, timezone.utc)
        if occurred > now() + timedelta(minutes=5):
            raise ValueError()
    except (ValueError, TypeError, OSError, OverflowError):
        raise APIError('Data de evento inválida.', 422) from None
    thread = (
        InboxThread.query.filter_by(
            workspace_id=connection.workspace_id, channel='instagram', address=connection.instagram_id + ':' + peer
        )
        .with_for_update()
        .first()
    )
    if not thread:
        thread = InboxThread(
            workspace_id=connection.workspace_id,
            channel='instagram',
            address=connection.instagram_id + ':' + peer,
            updated_at=occurred,
        )
        db.session.add(thread)
        db.session.flush()
    previous_updated = thread.updated_at
    # The provider MID, not the origin of the send, identifies the same message.
    existing = InboxMessage.query.filter_by(
        workspace_id=connection.workspace_id, thread_id=thread.id, provider_id=str(mid)[:180]
    ).first()
    if existing:
        if outgoing and existing.direction == 'out' and existing.status in ('sending', 'unknown'):
            existing.status, existing.error = 'sent', None
        return False
    if not outgoing:
        contact = db.session.get(Contact, thread.contact_id) if thread.contact_id else None
        if not contact:
            earlier = (
                InstagramComment.query.filter(
                    InstagramComment.connection_id == connection.id,
                    InstagramComment.from_id == peer,
                    InstagramComment.contact_id.isnot(None),
                )
                .order_by(InstagramComment.created_at)
                .first()
            )
            contact = db.session.get(Contact, earlier.contact_id) if earlier else None
            if contact and (contact.archived or contact.workspace_id != connection.workspace_id):
                contact = None
            if not contact:
                contact = Contact(
                    workspace_id=connection.workspace_id,
                    name='Instagram ' + peer,
                    source='Instagram',
                    custom_fields={'instagram_scoped_id': peer, 'instagram_account_id': connection.instagram_id},
                )
                db.session.add(contact)
                db.session.flush()
            thread.contact_id = contact.id
        if not historical and (contact.name.startswith('@') or contact.name == 'Instagram ' + peer):
            profiles.apply_profile(contact, peer, client.fetch_profile(connection, peer))
    row = InboxMessage(
        workspace_id=connection.workspace_id,
        thread_id=thread.id,
        direction='out' if outgoing else 'in',
        content=str(content)[:20000],
        status='sent' if outgoing else 'received',
        provider_id=str(mid)[:180],
        idempotency_key='instagram:' + key,
        created_at=occurred,
        scheduled_at=occurred,
    )
    db.session.add(row)
    db.session.flush()
    # Backfilled history must not move an old conversation ahead of newer messages.
    thread.updated_at = max(previous_updated, occurred)
    flag_modified(thread, 'updated_at')  # Override Base.onupdate, even when the date is unchanged.
    if not outgoing and not historical:
        thread.status = 'open'  # A new message reopens a closed conversation, as on WhatsApp.
        from ..notifications import record

        record(thread, row, 'inbox')
        contact = db.session.get(Contact, thread.contact_id)
        if contact and not contact.archived:
            from ..automations import received_reply

            received_reply(connection.workspace_id, contact, row.id)
    return True


def recover_outgoing_events(connection):
    """Replay preserved outbound events only; caller commits, no provider calls or automations."""
    workspace = db.session.get(Workspace, connection.workspace_id)
    if not connection.active or not workspace or not workspace.active:
        return 0
    restored = 0
    events = (
        InstagramEvent.query.filter_by(
            connection_id=connection.id, workspace_id=connection.workspace_id, kind='messaging'
        )
        .order_by(InstagramEvent.created_at)
        .all()
    )
    for event in events:
        item = event.payload or {}
        if str((item.get('sender') or {}).get('id', '')) == connection.instagram_id:
            restored += int(ingest_message(connection, item, event.event_key))
    return restored


def confirm_reply(row, provider_id):
    """An echo can arrive while the send HTTP call is still running. Keep the original platform claim."""
    InboxThread.query.filter_by(id=row.thread_id, workspace_id=row.workspace_id).with_for_update().one()
    echoes = (
        InboxMessage.query.filter_by(
            workspace_id=row.workspace_id, thread_id=row.thread_id, direction='out', provider_id=str(provider_id)[:180]
        )
        .filter(InboxMessage.id != row.id)
        .all()
    )
    for echo in echoes:
        if echo.idempotency_key.startswith('instagram:') and echo.sent_by_id is None:
            db.session.delete(echo)
    row.provider_id, row.status, row.error = str(provider_id)[:180], 'sent', None


def dm_message(text, buttons=None, quick_replies=None):
    """The Send API `message`: plain text, or a button template when there are link buttons; quick replies ride along."""
    if buttons:
        message = {
            'attachment': {
                'type': 'template',
                'payload': {
                    'template_type': 'button',
                    'text': text,
                    'buttons': [{'type': 'web_url', 'url': b['url'], 'title': b['title']} for b in buttons],
                },
            }
        }
    else:
        message = {'text': text}
    if quick_replies:
        message['quick_replies'] = [{'content_type': 'text', 'title': q, 'payload': q} for q in quick_replies]
    return message


def dm_record(text, buttons=None, quick_replies=None):
    """How a sent message with buttons reads in the inbox, which stores plain text."""
    lines = [text]
    if buttons:
        lines.append('Botões: ' + ' · '.join(f'{b["title"]} ({b["url"]})' for b in buttons))
    if quick_replies:
        lines.append('Respostas rápidas: ' + ' · '.join(quick_replies))
    return '\n\n'.join(lines)
