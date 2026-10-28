"""Receive-time notifications, with account- and user-scoped monotonic read cursors."""

from flask import g
from sqlalchemy import and_, func, or_

from ..common import get, query
from ..extensions import db
from ..models import Contact, InboxThread, MessageNotification, NotificationReadState, WhatsAppConversation
from .booking import lock


def record(thread, message, source):
    if message.direction != 'in' or message.workspace_id != thread.workspace_id:
        return
    contact = (
        Contact.query.filter_by(id=thread.contact_id, workspace_id=thread.workspace_id).first()
        if thread.contact_id
        else None
    )
    channel = 'whatsapp' if source == 'whatsapp' else thread.channel
    name = (
        contact.name
        if contact
        else getattr(thread, 'contact_name', None)
        or ('Instagram' if channel == 'instagram' else getattr(thread, 'address', None) or thread.phone)
    )
    db.session.add(
        MessageNotification(
            workspace_id=thread.workspace_id,
            source=source,
            thread_id=thread.id,
            message_id=message.id,
            channel=channel,
            sender_name=str(name)[:180],
            preview=' '.join(message.content.split())[:255],
        )
    )


def at_or_before(timestamp, identifier):
    return or_(
        MessageNotification.created_at < timestamp,
        and_(MessageNotification.created_at == timestamp, MessageNotification.id <= identifier),
    )


def unread():
    return (
        query(MessageNotification)
        .outerjoin(
            NotificationReadState,
            and_(
                NotificationReadState.workspace_id == MessageNotification.workspace_id,
                NotificationReadState.user_id == g.user.id,
                NotificationReadState.source == MessageNotification.source,
                NotificationReadState.thread_id == MessageNotification.thread_id,
            ),
        )
        .filter(
            or_(
                NotificationReadState.id.is_(None),
                MessageNotification.created_at > NotificationReadState.read_at,
                and_(
                    MessageNotification.created_at == NotificationReadState.read_at,
                    MessageNotification.id > NotificationReadState.read_id,
                ),
            )
        )
    )


def feed():
    # Freeze the upper bound before querying counts/items; arrivals during this request are picked up next time.
    latest = (
        query(MessageNotification)
        .order_by(MessageNotification.created_at.desc(), MessageNotification.id.desc())
        .first()
    )
    if not latest:
        return {'items': [], 'total_unread': 0, 'unread_threads': 0, 'cursor': None}
    q = unread().filter(at_or_before(latest.created_at, latest.id))
    partition = (MessageNotification.source, MessageNotification.thread_id)
    ranked = q.with_entities(
        MessageNotification.id.label('identifier'),
        func.row_number()
        .over(partition_by=partition, order_by=(MessageNotification.created_at.desc(), MessageNotification.id.desc()))
        .label('position'),
        func.count().over(partition_by=partition).label('unread_count'),
    ).subquery()
    heads = (
        db.session.query(MessageNotification, ranked.c.unread_count)
        .join(ranked, ranked.c.identifier == MessageNotification.id)
        .filter(ranked.c.position == 1)
        .order_by(MessageNotification.created_at.desc(), MessageNotification.id.desc())
        .limit(20)
        .all()
    )
    items = [
        {**row.to_dict(), 'created_at': row.created_at.isoformat(timespec='microseconds'), 'unread_count': count}
        for row, count in heads
    ]
    threads = db.session.query(func.count()).select_from(ranked).filter(ranked.c.position == 1).scalar()
    return {
        'items': items,
        'total_unread': q.count(),
        'unread_threads': threads,
        'cursor': {'id': latest.id, 'created_at': latest.created_at.isoformat(timespec='microseconds')},
    }


def advance(notification):
    lock(f'notification-read:{g.workspace_id}:{g.user.id}:{notification.source}:{notification.thread_id}')
    state = (
        query(NotificationReadState)
        .filter_by(user_id=g.user.id, source=notification.source, thread_id=notification.thread_id)
        .with_for_update()
        .first()
    )
    if not state:
        db.session.add(
            NotificationReadState(
                workspace_id=g.workspace_id,
                user_id=g.user.id,
                source=notification.source,
                thread_id=notification.thread_id,
                read_at=notification.created_at,
                read_id=notification.id,
            )
        )
    elif (notification.created_at, notification.id) > (state.read_at, state.read_id):
        state.read_at, state.read_id = notification.created_at, notification.id


def read_message(source, thread_id, message_id):
    get(WhatsAppConversation if source == 'whatsapp' else InboxThread, thread_id)
    notification = (
        query(MessageNotification).filter_by(source=source, thread_id=thread_id, message_id=message_id).first()
    )
    if notification:
        advance(notification)


def read_all():
    ranked = (
        query(MessageNotification)
        .with_entities(
            MessageNotification.id.label('identifier'),
            func.row_number()
            .over(
                partition_by=(MessageNotification.source, MessageNotification.thread_id),
                order_by=(MessageNotification.created_at.desc(), MessageNotification.id.desc()),
            )
            .label('position'),
        )
        .subquery()
    )
    rows = (
        db.session.query(MessageNotification)
        .join(ranked, ranked.c.identifier == MessageNotification.id)
        .filter(ranked.c.position == 1)
        .order_by(MessageNotification.source, MessageNotification.thread_id)
        .all()
    )
    for row in rows:
        advance(row)


def thread_counts():
    counts = {
        (source, thread_id): 0
        for source, thread_id in query(MessageNotification)
        .with_entities(MessageNotification.source, MessageNotification.thread_id)
        .distinct()
    }
    counts.update(
        {
            (source, thread_id): count
            for source, thread_id, count in unread()
            .with_entities(MessageNotification.source, MessageNotification.thread_id, func.count())
            .group_by(MessageNotification.source, MessageNotification.thread_id)
        }
    )
    return counts
