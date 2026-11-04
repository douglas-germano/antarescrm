"""Read models for the unified inbox. Account scope is explicit, independent of HTTP globals."""

from ..extensions import db
from ..models import Contact, InboxMessage, InboxThread, Opportunity, WhatsAppConversation, WhatsAppMessage
from ..tenancy import AccountContext
from . import notifications


def list_threads(account: AccountContext):
    """Every conversation across channels, newest first, with what the list needs to triage it."""
    items = []
    inbox_threads = account.query(InboxThread).order_by(InboxThread.updated_at.desc()).limit(200).all()
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
        last = (
            account.query(InboxMessage).filter_by(thread_id=thread.id).order_by(InboxMessage.created_at.desc()).first()
        )
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
        account.query(WhatsAppConversation)
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
    contacts = {c.id: c for c in account.query(Contact).filter(Contact.id.in_(contact_ids))} if contact_ids else {}
    open_deals = (
        {
            row[0]
            for row in account.query(Opportunity)
            .filter(Opportunity.contact_id.in_(contact_ids), Opportunity.status == 'open')
            .with_entities(Opportunity.contact_id)
        }
        if contact_ids
        else set()
    )
    counts = notifications.thread_counts(account)
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
