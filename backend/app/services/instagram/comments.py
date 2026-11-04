"""Instagram comments: comment ingestion and automated replies."""

from datetime import timedelta

from ...common import APIError
from ...extensions import db
from ...models import Contact, InboxMessage, InboxThread, InstagramComment, InstagramConnection, now
from . import client, messages

COMMENT_REPLIES_PER_HOUR = 60


def process_comment(connection, value):
    """Stores a top-level comment from someone else, links a contact, and fires `instagram.comment` automations."""
    comment_id, author = str(value.get('id') or ''), value.get('from') or {}
    sender, username = str(author.get('id') or ''), str(author.get('username') or '')[:150]
    if not comment_id or not sender.isdigit() or sender == connection.instagram_id or value.get('parent_id'):
        return  # Own comments and replies never trigger anything: no loops.
    if InstagramComment.query.filter_by(comment_id=comment_id).first():
        return
    contact = None
    thread = InboxThread.query.filter_by(
        workspace_id=connection.workspace_id, channel='instagram', address=connection.instagram_id + ':' + sender
    ).first()
    if thread and thread.contact_id:
        contact = db.session.get(Contact, thread.contact_id)
    if not contact:
        earlier = (
            InstagramComment.query.filter_by(connection_id=connection.id, from_id=sender)
            .filter(InstagramComment.contact_id.isnot(None))
            .first()
        )
        contact = db.session.get(Contact, earlier.contact_id) if earlier else None
    if contact and contact.archived:
        return
    if not contact:
        contact = Contact(
            workspace_id=connection.workspace_id,
            name=('@' + username) if username else 'Instagram ' + sender,
            source='Instagram',
            custom_fields={
                'instagram_scoped_id': sender,
                'instagram_account_id': connection.instagram_id,
                **({'instagram_username': username} if username else {}),
            },
        )
        db.session.add(contact)
        db.session.flush()
    row = InstagramComment(
        workspace_id=connection.workspace_id,
        connection_id=connection.id,
        comment_id=comment_id[:80],
        media_id=str((value.get('media') or {}).get('id') or '')[:80] or None,
        from_id=sender,
        username=username or None,
        text=str(value.get('text') or '')[:2200],
        contact_id=contact.id,
    )
    db.session.add(row)
    db.session.flush()
    from ..automations import emit

    emit(
        connection.workspace_id,
        'instagram.comment',
        comment_id,
        contact,
        source='Instagram',
        context={'text': row.text, 'media_id': row.media_id, 'comment_id': comment_id},
    )


def comment_action(kind, comment, contact, content, workspace, buttons=None, quick_replies=None):
    """Runs one automated comment action. Returns the comment id on success, or None when it no longer applies."""
    if not comment:
        raise APIError('Comentário indisponível.', 422)
    connection = InstagramConnection.query.filter_by(id=comment.connection_id, workspace_id=workspace.id).first()
    if not connection or not connection.active or (connection.expires_at and connection.expires_at <= now()):
        raise APIError('Reconecte o Instagram desta conta.', 409)
    sent_field = 'replied_at' if kind == 'reply_comment' else 'private_replied_at'
    if getattr(comment, sent_field):
        return None  # Already answered once; never answer the same comment twice.
    from sqlalchemy import func

    recent = (
        db.session.query(func.count(InstagramComment.id))
        .filter(
            InstagramComment.connection_id == connection.id,
            db.or_(
                InstagramComment.replied_at > now() - timedelta(hours=1),
                InstagramComment.private_replied_at > now() - timedelta(hours=1),
            ),
        )
        .scalar()
    )
    if recent >= COMMENT_REPLIES_PER_HOUR:
        raise APIError('Limite de respostas automáticas por hora atingido.', 429)
    from ..communications import render

    text = render(content, contact).replace('{{username}}', comment.username or '').strip()
    if not text or len(text.encode()) > 1000:
        raise APIError('Texto da resposta inválido.', 422)
    token = client.cipher().decrypt(connection.encrypted_token.encode()).decode()
    if kind == 'reply_comment':
        result = client.graph(comment.comment_id + '/replies', token, method='POST', params={'message': text})
        setattr(comment, sent_field, now())
        return comment.id
    result = client.graph(
        connection.instagram_id + '/messages',
        token,
        method='POST',
        json={
            'recipient': {'comment_id': comment.comment_id},
            'message': messages.dm_message(text, buttons, quick_replies),
        },
    )
    setattr(comment, sent_field, now())
    thread = InboxThread.query.filter_by(
        workspace_id=workspace.id, channel='instagram', address=connection.instagram_id + ':' + comment.from_id
    ).first()
    if not thread:
        thread = InboxThread(
            workspace_id=workspace.id,
            channel='instagram',
            address=connection.instagram_id + ':' + comment.from_id,
            contact_id=contact.id,
        )
        db.session.add(thread)
        db.session.flush()
    elif not thread.contact_id:
        thread.contact_id = contact.id
    message_id = str(result.get('message_id') or 'private-' + comment.comment_id)[:180]
    message = InboxMessage(
        workspace_id=workspace.id,
        thread_id=thread.id,
        direction='out',
        content=messages.dm_record(text, buttons, quick_replies),
        status='sent',
        provider_id=message_id,
        idempotency_key='instagram-private:' + comment.comment_id,
    )
    db.session.add(message)
    db.session.flush()
    messages.confirm_reply(message, message_id)
    thread.updated_at = now()
    return comment.id
