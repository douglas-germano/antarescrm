"""Application operations shared by channel-specific routes and the unified inbox."""

from ..common import APIError
from ..extensions import db
from ..models import Contact, InboxThread, MessageTemplate, WhatsAppConversation
from ..tenancy import AccountContext
from . import communications, instagram, whatsapp


def queue_broadcast(account: AccountContext, data):
    """Prepare the whole batch in the caller's transaction; never deliver to providers here."""
    template = account.get(MessageTemplate, data['template_id'])
    contacts = [account.get(Contact, identifier) for identifier in dict.fromkeys(data['contact_ids'])]
    if not communications.available(account.workspace_id, template.channel):
        raise APIError('Configure o canal no servidor antes de criar o disparo.', 503)
    return [
        communications.enqueue(
            account.workspace_id,
            contact,
            template.channel,
            communications.render(template.content, contact),
            communications.render(template.subject, contact),
            data['idempotency_key'] + ':' + contact.id,
            account.user_id,
        )
        for contact in contacts
    ]


def whatsapp_target(account: AccountContext, conversation_id):
    row = account.get(WhatsAppConversation, conversation_id)
    if row.status == 'closed':
        raise APIError('Reabra a conversa antes de enviar.', 409)
    return row


def send_whatsapp(account: AccountContext, conversation, content, key, file=None):
    if conversation.workspace_id != account.workspace_id:
        raise APIError('Registro não encontrado.', 404)
    if conversation.status == 'closed':
        raise APIError('Reabra a conversa antes de enviar.', 409)
    # send_outgoing owns the durable claim and outcome commits around the external call.
    return whatsapp.send_outgoing(
        whatsapp.connection_for(account.workspace_id), conversation, content, key, account.user_id, file
    )


def send_inbox_reply(account: AccountContext, thread_id, data):
    thread = account.get(InboxThread, thread_id)
    if thread.channel == 'instagram':
        return instagram.send_reply(thread, data['content'], data['idempotency_key'], account.user_id), 200
    if not thread.contact_id:
        raise APIError('Cadastre este remetente como contato antes de responder.', 422)
    contact = account.get(Contact, thread.contact_id)
    if not communications.available(account.workspace_id, thread.channel):
        raise APIError('Configure o canal no servidor antes de responder.', 503)
    row = communications.enqueue(
        account.workspace_id,
        contact,
        thread.channel,
        data['content'],
        thread.subject,
        data['idempotency_key'],
        account.user_id,
    )
    db.session.commit()  # Queue creation only; the dispatcher owns provider-delivery transactions.
    return row, 202
