"""Read models for the unified inbox. Account scope is explicit, independent of HTTP globals."""

from datetime import timedelta
from statistics import median

from ..extensions import db
from ..models import (
    Contact,
    InboxMessage,
    InboxThread,
    InstagramConnection,
    Opportunity,
    User,
    WhatsAppConversation,
    WhatsAppMessage,
    now,
)
from ..tenancy import AccountContext
from . import notifications

# Outgoing messages in these states did not reach the contact, or nobody knows whether they did.
FAILED_STATUSES = ('failed', 'error', 'blocked', 'unknown')
SUMMARY_DAYS = 7


def _iso(value):
    return value.isoformat() if value else None


def _latest(model, thread_col, at_col, ids, *where):
    """The newest message of each thread in one query (row_number per thread), instead of one query per thread."""
    if not ids:
        return {}
    rank = db.func.row_number().over(partition_by=thread_col, order_by=(at_col.desc(), model.id.desc())).label('rank')
    ranked = db.select(model.id.label('id'), rank).where(thread_col.in_(ids), *where).subquery()
    rows = db.session.query(model).join(ranked, ranked.c.id == model.id).filter(ranked.c.rank == 1).all()
    return {getattr(row, thread_col.key): row for row in rows}


def _waiting_since(model, thread_col, at_col, ids):
    """When the contact started waiting: their first message after the team's last reply, per thread."""
    if not ids:
        return {}
    last_out = (
        db.select(thread_col.label('thread_id'), db.func.max(at_col).label('at'))
        .where(thread_col.in_(ids), model.direction == 'out')
        .group_by(thread_col)
        .subquery()
    )
    rows = (
        db.session.query(thread_col, db.func.min(at_col))
        .outerjoin(last_out, last_out.c.thread_id == thread_col)
        .filter(thread_col.in_(ids), model.direction == 'in', db.or_(last_out.c.at.is_(None), at_col > last_out.c.at))
        .group_by(thread_col)
        .all()
    )
    return dict(rows)


def _message_state(model, thread_col, at_col, ids):
    last = _latest(model, thread_col, at_col, ids)
    last_out = _latest(model, thread_col, at_col, ids, model.direction == 'out')
    return last, last_out, _waiting_since(model, thread_col, at_col, ids)


def _queue_fields(status, last, last_out, waiting_since):
    """Who the conversation waits on, since when, and whether the team's last message failed to go out."""
    direction = last.direction if last else ''
    is_open = status != 'closed'
    waiting_on = None
    if is_open and direction == 'in':
        waiting_on = 'team'
    elif is_open and direction == 'out':
        waiting_on = 'contact'
    failed = bool(last_out and last_out.status in FAILED_STATUSES)
    return {
        'last_direction': direction,
        'waiting_on': waiting_on,
        'waiting_since': _iso(waiting_since) if waiting_on == 'team' else None,
        'delivery_failed': failed,
        'delivery_error': (last_out.error or 'Envio sem confirmação.') if failed else None,
    }


def list_threads(account: AccountContext):
    """Every conversation across channels, newest first, with what the list needs to triage it."""
    items = []
    inbox_threads = account.query(InboxThread).order_by(InboxThread.updated_at.desc()).limit(200).all()
    ids = [t.id for t in inbox_threads]
    last, last_out, waiting = _message_state(InboxMessage, InboxMessage.thread_id, InboxMessage.created_at, ids)
    last_in = (
        dict(
            db.session.query(InboxMessage.thread_id, db.func.max(InboxMessage.created_at))
            .filter(InboxMessage.thread_id.in_(ids), InboxMessage.direction == 'in')
            .group_by(InboxMessage.thread_id)
            .all()
        )
        if ids
        else {}
    )
    for thread in inbox_threads:
        row = last.get(thread.id)
        items.append(
            {
                **thread.to_dict(),
                'source': 'inbox',
                'preview': row.content[:255] if row else '',
                'last_status': row.status if row else '',
                'last_message_at': _iso(row.created_at) if row else None,
                'last_inbound_at': _iso(last_in.get(thread.id)),
                **_queue_fields(thread.status, row, last_out.get(thread.id), waiting.get(thread.id)),
            }
        )
    conversations = (
        account.query(WhatsAppConversation).order_by(WhatsAppConversation.last_message_at.desc()).limit(200).all()
    )
    ids = [c.id for c in conversations]
    last, last_out, waiting = _message_state(
        WhatsAppMessage, WhatsAppMessage.conversation_id, WhatsAppMessage.occurred_at, ids
    )
    for thread in conversations:
        items.append(
            {
                **thread.to_dict(),
                'source': 'whatsapp',
                'channel': 'whatsapp',
                'address': thread.phone,
                'preview': thread.last_message_preview or '',
                **_queue_fields(thread.status, last.get(thread.id), last_out.get(thread.id), waiting.get(thread.id)),
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
    owner_ids = {item['assigned_to_id'] for item in items if item.get('assigned_to_id')}
    owners = (
        dict(account.query(User).filter(User.id.in_(owner_ids)).with_entities(User.id, User.name).all())
        if owner_ids
        else {}
    )
    counts = notifications.thread_counts(account)
    accounts = (
        {row.instagram_id: row.username for row in account.query(InstagramConnection)}
        if any(item['channel'] == 'instagram' for item in items)
        else {}
    )
    for item in items:
        contact = contacts.get(item.get('contact_id'))
        item['has_open_deal'] = item.get('contact_id') in open_deals
        item['assigned_to_name'] = owners.get(item.get('assigned_to_id'))
        if item['channel'] == 'instagram':
            username = (contact.custom_fields or {}).get('instagram_username') if contact else None
            item['display_address'] = '@' + username if username else 'Instagram'
            # With several connected profiles, the inbox shows which one received the conversation.
            receiver = accounts.get(str(item.get('address') or '').split(':')[0])
            if receiver and len(accounts) > 1:
                item['instagram_account'] = receiver
        key = (item['source'], item['id'])
        if key in counts:
            item['unread_count'] = counts[key]
    items.sort(key=lambda row: row.get('last_message_at') or row.get('updated_at') or '', reverse=True)
    return {'items': items}


def _first_responses(account, model, thread_col, at_col, since):
    """Seconds between a contact's first unanswered message and the team's next reply that went out."""
    rows = (
        account.query(model)
        .filter(at_col >= since)
        .with_entities(thread_col, model.direction, model.status, at_col)
        .order_by(thread_col, at_col)
        .all()
    )
    return first_response_samples(rows)


def first_response_samples(rows):
    """Rows of (thread, direction, status, at), ordered by thread and time: one sample per answered wait."""
    samples, pending = [], {}
    for thread_id, direction, status, at in rows:
        if direction == 'in':
            pending.setdefault(thread_id, at)
        elif direction == 'out' and status not in FAILED_STATUSES and thread_id in pending:
            samples.append(max(0.0, (at - pending.pop(thread_id)).total_seconds()))
    return samples


def summary(account: AccountContext):
    """Counts for the inbox quick filters (open conversations only) and the median first response of the week."""
    items = [item for item in list_threads(account)['items'] if item.get('status') != 'closed']
    since = now() - timedelta(days=SUMMARY_DAYS)
    samples = _first_responses(
        account, InboxMessage, InboxMessage.thread_id, InboxMessage.created_at, since
    ) + _first_responses(account, WhatsAppMessage, WhatsAppMessage.conversation_id, WhatsAppMessage.occurred_at, since)
    return {
        'open': len(items),
        'mine': sum(1 for item in items if item.get('assigned_to_id') == account.user_id),
        'unassigned': sum(1 for item in items if not item.get('assigned_to_id')),
        'waiting_team': sum(1 for item in items if item.get('waiting_on') == 'team'),
        'delivery_failed': sum(1 for item in items if item.get('delivery_failed')),
        'first_response_median': round(median(samples)) if samples else None,
        'first_response_sample': len(samples),
        'period_days': SUMMARY_DAYS,
        'unit': 'seconds',
    }
