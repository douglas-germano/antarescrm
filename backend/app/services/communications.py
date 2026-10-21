"""Account-specific transport adapters and durable outbox.

Secrets live only in server configuration. No network calls occur in CRM transactions.
A send with an ambiguous outcome is never retried automatically.
"""

import re
import smtplib
import ssl
from email.message import EmailMessage

import requests
from flask import current_app
from marshmallow import ValidationError, fields

from ..access import workspace_role
from ..common import APIError
from ..extensions import db
from ..models import (
    AuditLog,
    AutomationJob,
    AutomationRule,
    AutomationRun,
    CommunicationSuppression,
    Contact,
    InboxMessage,
    InboxThread,
    User,
    WhatsAppConnection,
    Workspace,
    now,
)


def account_config(workspace_id, channel):
    return current_app.config.get('COMMUNICATION_ACCOUNTS', {}).get(workspace_id, {}).get(channel, {})


def available(workspace_id, channel):
    if channel == 'instagram':
        return False  # Only replies to inbound DMs, never bulk broadcasts or generic outbox.
    config = account_config(workspace_id, channel)
    if channel == 'email':
        return all(config.get(key) for key in ('host', 'from_address'))
    if channel == 'sms':
        return all(config.get(key) for key in ('account_sid', 'auth_token', 'from_number'))

    return bool(WhatsAppConnection.query.filter_by(workspace_id=workspace_id, state='open').first())


def address_for(contact, channel):
    if contact.archived:
        raise APIError('O contato está arquivado.', 422)
    address = (contact.email if channel == 'email' else contact.phone) or ''
    if channel == 'email':
        try:
            fields.Email().deserialize(address)
        except ValidationError:
            raise APIError('O contato precisa de um e-mail válido.', 422) from None
        return address.lower().strip()

    number = re.sub(r'[\s()+.\-]', '', address)
    if not number.isdigit() or not 8 <= len(number) <= 15:
        raise APIError('Informe o telefone completo, com código do país.', 422)
    return '+' + number


def render(text, contact):
    for key in ('name', 'email', 'phone'):
        text = text.replace('{{' + key + '}}', getattr(contact, key) or '')
    for key, value in (contact.custom_fields or {}).items():
        text = text.replace('{{custom.' + key + '}}', str(value))
    return text


def enqueue(workspace_id, contact, channel, content, subject, key, user_id=None, scheduled_at=None):
    if contact.workspace_id != workspace_id:
        raise APIError('Contato não encontrado nesta conta.', 404)

    if CommunicationSuppression.query.filter_by(
        workspace_id=workspace_id, contact_id=contact.id, channel=channel
    ).first():
        raise APIError('Contato não autoriza mensagens neste canal.', 409)
    address = address_for(contact, channel)
    existing = InboxMessage.query.filter_by(workspace_id=workspace_id, idempotency_key=key).first()
    if existing:
        thread = db.session.get(InboxThread, existing.thread_id)
        if (
            thread.channel != channel
            or thread.contact_id != contact.id
            or existing.content != content
            or existing.subject != subject
        ):
            raise APIError('Chave já utilizada para outra mensagem.', 409)
        return existing
    thread = InboxThread.query.filter_by(workspace_id=workspace_id, channel=channel, address=address).first()
    if not thread:
        thread = InboxThread(
            workspace_id=workspace_id, channel=channel, address=address, contact_id=contact.id, subject=subject
        )
        db.session.add(thread)
        db.session.flush()
    message = InboxMessage(
        workspace_id=workspace_id,
        thread_id=thread.id,
        direction='out',
        content=content,
        subject=subject,
        idempotency_key=key,
        sent_by_id=user_id,
        scheduled_at=scheduled_at or now(),
    )
    db.session.add(message)
    db.session.flush()
    db.session.add(
        AuditLog(
            workspace_id=workspace_id,
            user_id=user_id,
            action='queue_message',
            resource='inbox_messages',
            resource_id=message.id,
            details={'channel': channel},
        )
    )
    thread.updated_at = now()
    return message


def deliver(thread, message):
    config = account_config(thread.workspace_id, thread.channel)
    if thread.channel == 'email':
        mail = EmailMessage()
        mail['From'], mail['To'], mail['Subject'] = config['from_address'], thread.address, message.subject
        mail['Message-ID'] = '<' + message.id + '@antarescrm.local>'
        mail.set_content(message.content)
        smtp_type = smtplib.SMTP_SSL if config.get('ssl', True) else smtplib.SMTP
        options = {'timeout': 20}
        if config.get('ssl', True):
            options['context'] = ssl.create_default_context()
        with smtp_type(
            config['host'], int(config.get('port', 465 if config.get('ssl', True) else 587)), **options
        ) as smtp:
            if not config.get('ssl', True):
                smtp.starttls(context=ssl.create_default_context())
            if config.get('username'):
                smtp.login(config['username'], config['password'])
            smtp.send_message(mail)
        return str(mail['Message-ID'])
    if thread.channel == 'sms':
        sid = config['account_sid']
        response = requests.post(
            f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json',
            auth=(sid, config['auth_token']),
            data={'From': config['from_number'], 'To': thread.address, 'Body': message.content},
            timeout=(5, 20),
        )
        response.raise_for_status()
        return str(response.json()['sid'])
    from .whatsapp import connection_for, conversation_for, send_outgoing

    connection = connection_for(thread.workspace_id)
    conversation = conversation_for(connection, thread.address)
    if not conversation.contact_id:
        conversation.contact_id = thread.contact_id
    result, _ = send_outgoing(connection, conversation, message.content, 'inbox:' + message.id, message.sent_by_id)
    if result.status not in ('sent', 'delivered', 'read'):
        raise RuntimeError('WhatsApp send outcome is unknown')
    return result.provider_id


def dispatch(workspace_id=None, limit=20):
    processed = []
    for _ in range(limit):
        q = InboxMessage.query.filter(
            InboxMessage.direction == 'out', InboxMessage.status == 'queued', InboxMessage.scheduled_at <= now()
        )
        if workspace_id:
            q = q.filter_by(workspace_id=workspace_id)
        message = q.order_by(InboxMessage.scheduled_at).with_for_update(skip_locked=True).first()
        if not message:
            break
        thread = db.session.get(InboxThread, message.thread_id)
        workspace = db.session.get(Workspace, message.workspace_id)
        contact = db.session.get(Contact, thread.contact_id) if thread.contact_id else None

        user = db.session.get(User, message.sent_by_id) if message.sent_by_id else None
        automation_active = True
        if message.idempotency_key.startswith('automation:'):
            job = db.session.get(AutomationJob, message.idempotency_key.split(':', 1)[1])
            run = db.session.get(AutomationRun, job.run_id) if job else None
            rule = db.session.get(AutomationRule, run.rule_id) if run else None
            automation_active = bool(rule and rule.active and rule.workspace_id == message.workspace_id)
        if (
            not automation_active
            or not workspace
            or not workspace.active
            or not contact
            or contact.archived
            or (message.sent_by_id and (not user or not workspace_role(user, workspace)))
        ):
            message.status, message.error = 'cancelled', 'Contato ou acesso à conta indisponível.'
            db.session.commit()
            processed.append(message.to_dict())
            continue

        suppressed = CommunicationSuppression.query.filter_by(
            workspace_id=message.workspace_id, contact_id=contact.id, channel=thread.channel
        ).first()
        if suppressed:
            message.status, message.error = 'cancelled', 'Contato não autoriza mensagens neste canal.'
            db.session.commit()
            processed.append(message.to_dict())
            continue
        if not available(message.workspace_id, thread.channel):
            # Keep queued until configured, without blocking other accounts/channels.
            message.status, message.error = 'blocked', 'Configure o canal no servidor antes de reenfileirar.'
            db.session.commit()
            processed.append(message.to_dict())
            continue
        message.status = 'sending'
        db.session.commit()  # Crash-safe claim before external I/O. Never automatically resend sending/unknown.
        try:
            message.provider_id = deliver(thread, message)
            message.status, message.error = 'sent', None
        except Exception as error:  # delivery boundary: any failure leaves the message 'unknown'
            # Provider errors may include secrets; never persist their raw response.
            current_app.logger.warning('Falha ao entregar a mensagem %s: %s', message.id, type(error).__name__)
            db.session.rollback()
            message = db.session.get(InboxMessage, message.id)
            message.status, message.error = 'unknown', 'Envio sem confirmação. Verifique no provedor antes de reenviar.'
        db.session.add(
            AuditLog(
                workspace_id=message.workspace_id,
                user_id=message.sent_by_id,
                action='dispatch_message',
                resource='inbox_messages',
                resource_id=message.id,
                details={'status': message.status},
            )
        )
        db.session.commit()
        processed.append(message.to_dict())
    return processed
