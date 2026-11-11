"""Bridge automation events to the Atlas queue without calling providers."""

from datetime import timedelta

from ..access import account_users, workspace_role
from ..common import APIError
from ..extensions import db
from ..models import (
    AtlasJob,
    AtlasTarget,
    AutomationJob,
    AutomationRule,
    AutomationRun,
    CommunicationSuppression,
    Contact,
    FormSubmission,
    InboxMessage,
    InboxThread,
    LeadForm,
    Opportunity,
    PipelineStage,
    StageHistory,
    User,
    WhatsAppConnection,
    WhatsAppConversation,
    WhatsAppMessage,
    now,
)
from ..tenancy import AccountContext
from . import atlas, atlas_oauth
from .booking import lock
from .instagram.connections import active_connections, thread_connection
from .whatsapp import normalize_phone, phone_variants

DEFAULT_GOAL = 'Atenda o contato usando o contexto da conversa. Se faltar informação, faça uma pergunta breve.'


def inbound(workspace_id, contact_id, channel, trigger_id):
    if channel == 'whatsapp':
        message = WhatsAppMessage.query.filter_by(
            workspace_id=workspace_id, id=trigger_id, direction='in', status='received'
        ).first()
        if message and message.kind in ('text', 'audio') and message.content.strip():
            return WhatsAppConversation.query.filter_by(
                workspace_id=workspace_id, id=message.conversation_id, contact_id=contact_id
            ).first()
    elif channel == 'instagram':
        message = InboxMessage.query.filter_by(
            workspace_id=workspace_id, id=trigger_id, direction='in', status='received'
        ).first()
        if message and message.content.strip():
            return InboxThread.query.filter_by(
                workspace_id=workspace_id, id=message.thread_id, contact_id=contact_id, channel='instagram'
            ).first()
    return None


def open_conversation(workspace_id, contact_id, channel):
    if channel == 'whatsapp':
        return (
            WhatsAppConversation.query.filter_by(workspace_id=workspace_id, contact_id=contact_id)
            .filter(WhatsAppConversation.status != 'closed')
            .order_by(WhatsAppConversation.last_message_at.desc().nulls_last(), WhatsAppConversation.id)
            .first()
        )
    accounts = [row.instagram_id for row in active_connections(workspace_id)]
    if not accounts:
        raise APIError('Reconecte o Instagram desta conta.', 409)
    return (
        InboxThread.query.filter_by(workspace_id=workspace_id, contact_id=contact_id, channel='instagram')
        .filter(
            InboxThread.status != 'closed',
            db.or_(*[InboxThread.address.startswith(key + ':') for key in accounts]),
        )
        .order_by(InboxThread.updated_at.desc(), InboxThread.id)
        .first()
    )


def latest_inbound(row, channel):
    if channel == 'whatsapp':
        return (
            db.session.query(db.func.max(WhatsAppMessage.occurred_at))
            .filter_by(workspace_id=row.workspace_id, conversation_id=row.id, direction='in', status='received')
            .scalar()
        )
    return (
        db.session.query(db.func.max(InboxMessage.created_at))
        .filter_by(workspace_id=row.workspace_id, thread_id=row.id, direction='in', status='received')
        .scalar()
    )


def validate_channel(row, channel):
    if CommunicationSuppression.query.filter_by(
        workspace_id=row.workspace_id, contact_id=row.contact_id, channel=channel
    ).first():
        raise APIError('Contato bloqueado para mensagens neste canal.', 409)
    if channel == 'whatsapp':
        if not WhatsAppConnection.query.filter_by(workspace_id=row.workspace_id, state='open').first():
            raise APIError('Conecte o WhatsApp deste workspace.', 409)
    else:
        thread_connection(row)  # Raises when the account that owns the conversation is no longer connected.


def event_details(run, action, contact, deal, row, channel):
    if action['trigger_event'] == 'form.submitted':
        submission = FormSubmission.query.filter_by(
            workspace_id=run.workspace_id,
            id=run.event_key,
            contact_id=contact.id,
            opportunity_id=action.get('opportunity_id'),
        ).first()
        form = (
            LeadForm.query.filter_by(workspace_id=run.workspace_id, id=submission.form_id).first()
            if submission
            else None
        )
        if not form or not submission.consent_text:
            raise APIError('Envio de formulário indisponível.', 409)
        answers = submission.answers or {}
        if (
            channel == 'whatsapp'
            and answers.get('phone')
            and row.phone not in phone_variants(normalize_phone(answers['phone']))
        ):
            raise APIError('O telefone do formulário não corresponde à conversa vinculada.', 409)
        fields = [
            {'campo': field['label'], 'resposta': str(answers[field['key']])[:400]}
            for field in form.fields or []
            if field['key'] in answers and field['key'] not in ('name', 'email', 'phone')
        ][:12]
        return {'formulario': form.name, 'nome': answers.get('name') or contact.name, 'respostas': fields}
    if not deal or deal.status != 'open' or deal.contact_id != contact.id:
        raise APIError('Negócio indisponível para retorno.', 409)
    latest = (
        StageHistory.query.filter_by(workspace_id=run.workspace_id, opportunity_id=deal.id)
        .order_by(StageHistory.created_at.desc(), StageHistory.id.desc())
        .first()
    )
    if not latest or latest.id != run.event_key or latest.to_stage_id != deal.stage_id:
        raise APIError('O negócio já mudou de etapa.', 409)
    stage = PipelineStage.query.filter_by(workspace_id=run.workspace_id, id=deal.stage_id).first()
    if not stage:
        raise APIError('Etapa indisponível para retorno.', 409)
    return {'negocio': deal.title, 'etapa': stage.name}


def validate_outreach(run, action, contact, deal, row, channel):
    if not contact or contact.archived or row.contact_id != contact.id:
        raise APIError('Contato indisponível para retorno.', 409)
    validate_channel(row, channel)
    last = latest_inbound(row, channel)
    if not last or last <= now() - timedelta(hours=24):
        raise APIError('A conversa está fora da janela de 24 horas.', 409)
    if (run.config_snapshot or {}).get('stop_on_reply') and (last >= run.created_at or run.status == 'cancelled'):
        raise APIError('O contato já respondeu. Retorno do Atlas dispensado.', 409)
    return event_details(run, action, contact, deal, row, channel)


def opening_context(atlas_job, row, channel):
    workspace_id = atlas_job.workspace_id
    job = AutomationJob.query.filter_by(id=atlas_job.automation_context['job_id'], workspace_id=workspace_id).first()
    run = AutomationRun.query.filter_by(id=job.run_id, workspace_id=workspace_id).first() if job else None
    rule = (
        AutomationRule.query.filter_by(id=run.rule_id, workspace_id=workspace_id, active=True).first() if run else None
    )
    if not rule:
        raise APIError('A automação do Atlas está pausada ou indisponível.', 409)
    contact = Contact.query.filter_by(workspace_id=workspace_id, id=run.contact_id).first()
    deal = Opportunity.query.filter_by(workspace_id=workspace_id, id=job.action.get('opportunity_id')).first()
    return validate_outreach(run, job.action, contact, deal, row, channel)


def queue(job, run, contact, workspace, deal):
    action = job.action
    event = action.get('trigger_event')
    incoming = event == 'message.received'
    channel = action.get('inbound_channel' if incoming else 'atlas_channel')
    if event not in ('message.received', 'form.submitted', 'opportunity.stage_changed') or channel not in (
        'whatsapp',
        'instagram',
    ):
        job.detail = 'O evento não tem uma conversa compatível com o Atlas.'
        return None

    lock('atlas:' + workspace.id)
    user = next((u for u in account_users(workspace.id) if workspace_role(u, workspace) in ('owner', 'admin')), None)
    if not user or not atlas_oauth.status(workspace.id)['connected']:
        job.detail = 'Conecte o ChatGPT nas configurações do Atlas.'
        return None
    account = AccountContext(workspace.id, user.id)
    try:
        row = (
            inbound(workspace.id, contact.id, channel, run.event_key)
            if incoming
            else open_conversation(workspace.id, contact.id, channel)
        )
        if not row:
            raise APIError('Nenhuma conversa vinculada e disponível neste canal.', 409)
        atlas.conversation(account, channel, row.id)
        if incoming:
            validate_channel(row, channel)
        else:
            validate_outreach(run, action, contact, deal, row, channel)
    except APIError as error:
        job.detail = error.message
        return None

    target = atlas.assignment_target(account, channel, row.id)
    if not target:
        target_id = atlas.enroll(account, channel, row.id, DEFAULT_GOAL, opening=False, commit=False)
        target = db.session.get(AtlasTarget, target_id)
    if not target.active and AtlasJob.query.filter_by(target_id=target.id, status='handoff').first():
        job.detail = 'A conversa foi encaminhada para a equipe. Reatribua ao Atlas pela Caixa de Entrada.'
        return None
    if not target.active or not workspace_role(db.session.get(User, target.user_id), workspace):
        target.active, target.user_id = True, user.id
    queued = AtlasJob.query.filter_by(target_id=target.id, trigger_id=run.event_key).first()
    context = {
        'opening': not incoming,
        'job_id': job.id,
        'goal': action.get('content'),
        'opportunity_id': deal.id if deal else None,
    }
    if not queued:
        queued = atlas.enqueue(target, run.event_key, automation_context=context)
        db.session.flush()
        job.detail = 'Conversa atribuída ao Atlas. Mensagem em processamento.'
    else:
        if queued.status == 'queued' and not queued.automation_context:
            queued.automation_context = context
        job.detail = 'O Atlas já recebeu este evento.'
    return queued.id
