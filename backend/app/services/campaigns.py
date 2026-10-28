"""Explicitly prepared marketing campaigns. Preparing or refreshing never sends email."""

import hashlib
import hmac
import json
from html import escape

from flask import current_app
from marshmallow import ValidationError, fields
from sqlalchemy import func

from ..common import APIError
from ..extensions import db
from ..models import (
    BrevoEvent,
    CampaignRecipient,
    CommunicationSuppression,
    Contact,
    EmailCampaign,
    Workspace,
    now,
)
from . import brevo, campaigns_whatsapp

MAX_RECIPIENTS = 1000


def audience(workspace_id, filters, channel='email'):
    if channel == 'whatsapp':
        return campaigns_whatsapp.audience(workspace_id, filters)
    rows = Contact.query.filter_by(workspace_id=workspace_id, archived=False)
    if filters.get('source'):
        rows = rows.filter_by(source=filters['source'])
    suppressed = {
        row.contact_id for row in CommunicationSuppression.query.filter_by(workspace_id=workspace_id, channel='email')
    }
    suppressed_emails = {
        str(email).strip().lower()
        for (email,) in db.session.query(Contact.email).filter(
            Contact.workspace_id == workspace_id, Contact.id.in_(suppressed), Contact.email.isnot(None)
        )
    }
    eligible, emails = [], set()
    counts = {'without_email': 0, 'invalid': 0, 'suppressed': 0, 'duplicates': 0}
    for row in rows.order_by(Contact.id):
        if filters.get('tag') and filters['tag'] not in (row.tags or []):
            continue
        email = (row.email or '').strip().lower()
        if not email:
            counts['without_email'] += 1
            continue
        try:
            fields.Email().deserialize(email)
        except ValidationError:
            counts['invalid'] += 1
            continue
        if row.id in suppressed or email in suppressed_emails:
            counts['suppressed'] += 1
            continue
        if email in emails:
            counts['duplicates'] += 1
            continue
        emails.add(email)
        eligible.append({'contact_id': row.id, 'email': email, 'name': row.name})
    return eligible, counts


def fingerprint(rows):
    return hashlib.sha256(json.dumps(sorted(row.get('email') or row['phone'] for row in rows)).encode()).hexdigest()


def serialize(row):
    result = row.to_dict()
    if row.channel == 'whatsapp':
        result['status'], result['metrics'] = campaigns_whatsapp.progress(row)
        return result
    recipients = CampaignRecipient.query.filter_by(workspace_id=row.workspace_id, campaign_id=row.id).all()
    result['metrics'] = {
        kind: sum(kind in (item.events or {}) for item in recipients)
        for kind in ('delivered', 'opened', 'click', 'hard_bounce', 'soft_bounce', 'spam', 'unsubscribed')
    }
    return result


def bound_connection(row):
    connection = brevo.connection(row.workspace_id)
    if row.connection_id and (row.connection_id != connection.id or row.connection_version != connection.version):
        raise APIError('A conexão Brevo mudou. Crie uma nova campanha para usar a conexão atual.', 409)
    return connection


def prepare(row):
    if row.channel == 'whatsapp':
        return campaigns_whatsapp.prepare(row)
    connection = bound_connection(row)
    if row.status != 'draft':
        return row
    if not connection.webhook_id:
        raise APIError('Ative o acompanhamento do Brevo em Conexões antes de preparar campanhas.', 409)
    rows, _ = audience(row.workspace_id, row.audience)
    if not rows or len(rows) > MAX_RECIPIENTS:
        raise APIError(f'Selecione de 1 a {MAX_RECIPIENTS} e-mails válidos. Use tags ou origem para segmentar.', 422)
    row.connection_id, row.connection_version = connection.id, connection.version
    row.audience_hash, row.recipient_count, row.status = fingerprint(rows), len(rows), 'preparing'
    for item in rows:
        db.session.add(
            CampaignRecipient(
                workspace_id=row.workspace_id, campaign_id=row.id, contact_id=item['contact_id'], email=item['email']
            )
        )
    key = brevo.key_for(connection)
    db.session.commit()  # One durable claim before any provider mutations.
    try:
        if not connection.folder_id:
            connection.folder_id = int(
                brevo.api(key, 'contacts/folders', 'POST', json={'name': 'Antares ' + row.workspace_id})['id']
            )
            db.session.commit()
        row.list_id = int(
            brevo.api(
                key, 'contacts/lists', 'POST', json={'name': 'Antares ' + row.id, 'folderId': connection.folder_id}
            )['id']
        )
        db.session.commit()
        # Existing subscribers and blocklists are left intact. Membership is added separately after import completes.
        result = brevo.api(
            key,
            'contacts/import',
            'POST',
            json={
                'jsonBody': [{'email': item['email']} for item in rows],
                'listIds': [row.list_id],
                'updateExistingContacts': False,
                'disableNotification': True,
            },
        )
        row.process_id = int(result['processId'])
        row.status = 'importing'
    except Exception as error:
        current_app.logger.warning('Preparação de campanha sem confirmação: %s', type(error).__name__)
        row.status, row.error = (
            'unknown',
            'Preparação sem confirmação. Confira a campanha no Brevo antes de criar outra.',
        )
    db.session.commit()
    return row


def refresh(row):
    if row.channel == 'whatsapp':
        row.status, _ = campaigns_whatsapp.progress(row)
        return row
    connection = bound_connection(row)
    key = brevo.key_for(connection)
    if row.status == 'importing':
        result = brevo.api(key, 'processes/' + str(row.process_id))
        if result.get('status') in ('queued', 'processing'):
            return row
        if result.get('status') != 'completed':
            row.status, row.error = 'failed', 'A importação não foi concluída no Brevo.'
        else:
            # Claim creation before external I/O. A timeout cannot cause an automatic duplicate draft.
            row.status = 'preparing'
            db.session.commit()
            try:
                recipients = CampaignRecipient.query.filter_by(workspace_id=row.workspace_id, campaign_id=row.id).all()
                for start in range(0, len(recipients), 150):
                    brevo.api(
                        key,
                        f'contacts/lists/{row.list_id}/contacts/add',
                        'POST',
                        json={'emails': [item.email for item in recipients[start : start + 150]]},
                    )
                html = (
                    '<html><body><div style="white-space:pre-wrap">'
                    + escape(row.content).replace('\n', '<br>')
                    + '</div><p><a href="{{ unsubscribe }}">Cancelar inscrição</a></p></body></html>'
                )
                result = brevo.api(
                    key,
                    'emailCampaigns',
                    'POST',
                    json={
                        'name': row.name,
                        'subject': row.subject,
                        'sender': {'email': connection.sender_email, 'name': connection.sender_name},
                        'replyTo': connection.sender_email,
                        'type': 'classic',
                        'htmlContent': html,
                        'recipients': {'listIds': [row.list_id]},
                        'tag': 'antares-' + row.id,
                    },
                )
                row.provider_id, row.status, row.error = int(result['id']), 'ready', None
            except Exception as error:
                current_app.logger.warning('Criação de campanha sem confirmação: %s', type(error).__name__)
                row.status, row.error = (
                    'unknown',
                    'Criação sem confirmação. Confira o rascunho no Brevo antes de criar outro.',
                )
    elif row.provider_id:
        result = brevo.api(key, 'emailCampaigns/' + str(row.provider_id))
        remote = result.get('status')
        if remote in ('sent', 'queued', 'suspended', 'inProcess'):
            row.status = {'queued': 'sending', 'inProcess': 'sending'}.get(remote, remote)
        # Never turn an ambiguous send back into a sendable draft automatically.
    db.session.commit()
    return row


def send(row, audience_hash, user_id=None):
    if row.channel == 'whatsapp':
        return campaigns_whatsapp.send(row, audience_hash, user_id)
    connection = bound_connection(row)
    if row.status in ('sending', 'sent'):
        return row
    if row.status != 'ready' or not row.provider_id:
        raise APIError('Prepare a campanha e aguarde a importação antes de enviar.', 409)
    rows, _ = audience(row.workspace_id, row.audience)
    if not hmac.compare_digest(row.audience_hash or '', audience_hash) or fingerprint(rows) != row.audience_hash:
        raise APIError('O público mudou. Crie um novo rascunho e revise os destinatários.', 409)
    # Ensure the snapshot still points at the same active, allowed contacts, including duplicate-address changes.
    eligible = {(item['contact_id'], item['email']) for item in rows}
    recipients = CampaignRecipient.query.filter_by(workspace_id=row.workspace_id, campaign_id=row.id).all()
    if eligible != {(item.contact_id, item.email) for item in recipients}:
        raise APIError('Os contatos da campanha mudaram. Prepare um novo rascunho.', 409)
    key = brevo.key_for(connection)
    row.status, row.sent_at = 'sending', now()
    db.session.commit()
    try:
        brevo.api(key, f'emailCampaigns/{row.provider_id}/sendNow', 'POST')
        for recipient in recipients:
            if recipient.status == 'prepared':
                recipient.status = 'sent'
    except Exception as error:
        current_app.logger.warning('Envio de campanha sem confirmação: %s', type(error).__name__)
        row.status, row.error = 'unknown', 'Envio sem confirmação. Consulte o Brevo antes de qualquer novo envio.'
    db.session.commit()
    return row


def receive(connection, body):
    if not isinstance(body, dict):
        raise APIError('Evento inválido.', 422)
    workspace = db.session.get(Workspace, connection.workspace_id)
    if not workspace or not workspace.active:
        return
    kind = str(body.get('event') or '')
    aliases = {'hardBounce': 'hard_bounce', 'softBounce': 'soft_bounce', 'clicked': 'click', 'unique_opened': 'opened'}
    kind = aliases.get(kind, kind)
    if kind not in ('delivered', 'opened', 'click', 'hard_bounce', 'soft_bounce', 'spam', 'unsubscribed'):
        return
    campaign = EmailCampaign.query.filter_by(
        channel='email',
        workspace_id=connection.workspace_id,
        connection_id=connection.id,
        connection_version=connection.version,
        provider_id=body.get('camp_id'),
    ).first()
    email = str(body.get('email') or '').strip().lower()
    if not campaign or not email:
        return
    recipient = CampaignRecipient.query.filter_by(
        workspace_id=connection.workspace_id, campaign_id=campaign.id, email=email
    ).first()
    if not recipient:
        return
    digest = hashlib.sha256((connection.id + json.dumps(body, sort_keys=True)).encode()).hexdigest()
    if BrevoEvent.query.filter_by(event_key=digest).first():
        return
    db.session.add(
        BrevoEvent(
            workspace_id=connection.workspace_id,
            connection_id=connection.id,
            event_key=digest,
            campaign_id=campaign.id,
            kind=kind,
            email=email,
        )
    )
    recipient.events = {**(recipient.events or {}), kind: True}
    rank = {
        'prepared': 0,
        'sent': 1,
        'soft_bounce': 2,
        'delivered': 3,
        'opened': 4,
        'click': 5,
        'hard_bounce': 6,
        'spam': 7,
        'unsubscribed': 8,
    }
    if rank[kind] > rank.get(recipient.status, 0):
        recipient.status = kind
    if kind in ('unsubscribed', 'spam', 'hard_bounce'):
        # Block every local duplicate of this address, not just the row selected for this campaign.
        for contact in Contact.query.filter(
            Contact.workspace_id == connection.workspace_id, func.lower(func.trim(Contact.email)) == email
        ):
            if not CommunicationSuppression.query.filter_by(
                workspace_id=connection.workspace_id, contact_id=contact.id, channel='email'
            ).first():
                db.session.add(
                    CommunicationSuppression(
                        workspace_id=connection.workspace_id,
                        contact_id=contact.id,
                        channel='email',
                        reason='Brevo: ' + kind,
                    )
                )
