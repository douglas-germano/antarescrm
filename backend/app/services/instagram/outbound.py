"""Instagram outbound: direct-message delivery and automation orchestration."""

from datetime import timedelta

from flask import current_app

from ...common import APIError
from ...extensions import db
from ...models import CommunicationSuppression, Contact, InboxMessage, InboxThread, now
from ..delivery_transactions import commit_delivery
from . import client, connections, messages


def automation_message(contact, content, workspace, key, buttons=None, quick_replies=None):
    """An automated direct message in the contact's Instagram conversation. Returns None when there is no
    conversation or Instagram's 24-hour window has closed: those steps are dismissed, not failed."""
    accounts = {row.instagram_id: row for row in connections.active_connections(workspace.id)}
    if not accounts:
        raise APIError('Reconecte o Instagram desta conta.', 409)
    # The contact's most recent conversation on any connected account answers through that same account.
    thread = (
        InboxThread.query.filter_by(workspace_id=workspace.id, channel='instagram', contact_id=contact.id)
        .filter(db.or_(*[InboxThread.address.startswith(key + ':') for key in accounts]))
        .order_by(InboxThread.updated_at.desc())
        .first()
    )
    if not thread:
        return None
    connection = accounts[thread.address.split(':')[0]]
    last = (
        InboxMessage.query.filter_by(workspace_id=workspace.id, thread_id=thread.id, direction='in')
        .order_by(InboxMessage.created_at.desc())
        .first()
    )
    if not last or last.created_at < now() - timedelta(hours=24):
        return None
    if CommunicationSuppression.query.filter_by(
        workspace_id=workspace.id, contact_id=contact.id, channel='instagram'
    ).first():
        return None
    existing = InboxMessage.query.filter_by(workspace_id=workspace.id, idempotency_key=key).first()
    if existing:
        return existing.id
    from ..communications import render

    text = render(content, contact).strip()
    if not text or len(text.encode()) > 1000:
        raise APIError('Texto da mensagem inválido.', 422)
    result = client.graph(
        connection.instagram_id + '/messages',
        client.cipher().decrypt(connection.encrypted_token.encode()).decode(),
        method='POST',
        json={
            'recipient': {'id': thread.address.split(':')[1]},
            'message': messages.dm_message(text, buttons, quick_replies),
        },
    )
    if not result.get('message_id'):
        raise APIError('Sem confirmação do Instagram.', 502)
    row = InboxMessage(
        workspace_id=workspace.id,
        thread_id=thread.id,
        direction='out',
        content=messages.dm_record(text, buttons, quick_replies),
        status='sent',
        idempotency_key=key,
    )
    db.session.add(row)
    db.session.flush()
    messages.confirm_reply(row, result['message_id'])
    thread.updated_at = now()
    return row.id


def send_reply(thread, content, key, user_id):
    if len(content) > 1000:
        raise APIError('A resposta do Instagram aceita até 1.000 caracteres.', 422)
    connection = connections.thread_connection(thread)
    existing = InboxMessage.query.filter_by(workspace_id=thread.workspace_id, idempotency_key=key).first()
    if existing:
        if existing.thread_id != thread.id or existing.direction != 'out' or existing.content != content:
            raise APIError('Chave utilizada por outra mensagem.', 409)
        return existing
    last = (
        InboxMessage.query.filter_by(workspace_id=thread.workspace_id, thread_id=thread.id, direction='in')
        .order_by(InboxMessage.created_at.desc())
        .first()
    )
    if not last or last.created_at < now() - timedelta(hours=24):
        raise APIError('A janela de resposta de 24 horas do Instagram encerrou. Aguarde uma nova mensagem.', 409)
    contact = db.session.get(Contact, thread.contact_id)

    if (
        not contact
        or contact.archived
        or CommunicationSuppression.query.filter_by(
            workspace_id=thread.workspace_id, contact_id=contact.id, channel='instagram'
        ).first()
    ):
        raise APIError('Este contato está indisponível para respostas.', 409)
    row = InboxMessage(
        workspace_id=thread.workspace_id,
        thread_id=thread.id,
        direction='out',
        content=content,
        status='sending',
        idempotency_key=key,
        sent_by_id=user_id,
    )
    db.session.add(row)
    commit_delivery(
        'claim', channel='instagram', workspace_id=thread.workspace_id, resource_id=row.id
    )  # Persist claim before external I/O; never retry an ambiguous outcome.
    try:
        result = client.graph(
            connection.instagram_id + '/messages',
            client.cipher().decrypt(connection.encrypted_token.encode()).decode(),
            method='POST',
            json={'recipient': {'id': thread.address.split(':')[1]}, 'message': {'text': content}},
        )
        if not result.get('message_id'):
            raise APIError('Sem confirmação.', 502)
        messages.confirm_reply(row, result['message_id'])
    except Exception as error:  # delivery boundary: any failure after the call leaves the message 'unknown'
        current_app.logger.warning('Falha ao enviar resposta no Instagram: %s', type(error).__name__)
        row.status, row.error = 'unknown', 'Envio sem confirmação. Confira no Instagram antes de reenviar.'
    thread.updated_at = now()
    commit_delivery('outcome', channel='instagram', workspace_id=thread.workspace_id, resource_id=row.id)
    return row
