"""Account-scoped workflow execution. Database actions are atomic; outbound I/O uses the outbox."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from flask import current_app
from sqlalchemy.orm import aliased

from ..access import account_users
from ..common import APIError
from ..extensions import db
from ..models import (
    Activity,
    AuditLog,
    AutomationJob,
    AutomationRule,
    AutomationRun,
    Booking,
    Contact,
    InboxMessage,
    InboxThread,
    InstagramComment,
    MessageTemplate,
    Opportunity,
    PipelineStage,
    StageHistory,
    Task,
    WhatsAppConversation,
    WhatsAppMessage,
    Workspace,
    now,
)
from .conditions import matches


def assignee_available(rule):
    return not rule.assignee_id or rule.assignee_id in {u.id for u in account_users(rule.workspace_id) if u.active}


def log(workspace_id, action, row, details=None):
    db.session.add(
        AuditLog(
            workspace_id=workspace_id,
            action=action,
            resource=row.__tablename__,
            resource_id=row.id,
            details=details or {},
        )
    )


def task_defaults(assignee_id, context):
    handoff = (context or {}).get('atlas_handoff') or {}
    return {
        'assignee_id': assignee_id or handoff.get('assignee_id'),
        'description': handoff.get('summary'),
    }


def emit(workspace_id, event, event_key, contact, opportunity_id=None, source=None, context=None):
    """`context` carries event data for conditions (e.g. the Instagram comment text) and is never stored in rules."""
    workspace = db.session.get(Workspace, workspace_id)
    if not workspace or not workspace.active or not contact or contact.workspace_id != workspace_id:
        return
    deal = Opportunity.query.filter_by(id=opportunity_id, workspace_id=workspace_id).first() if opportunity_id else None
    if deal and event in ('opportunity.created', 'opportunity.stage_changed'):
        entry = stage_entry(deal)
        emit(workspace_id, 'opportunity.stage_idle', entry, contact, deal.id, source)
    rules = AutomationRule.query.filter_by(workspace_id=workspace_id, event=event, active=True).all()
    for rule in rules:
        if rule.source and rule.source.casefold() != (source or contact.source or '').casefold():
            continue
        if not matches(rule.conditions, contact, deal, context):
            continue
        if rule.required_tag and rule.required_tag not in (contact.tags or []):
            continue
        if AutomationRun.query.filter_by(rule_id=rule.id, event_key=str(event_key)).first():
            continue
        run = AutomationRun(
            workspace_id=workspace_id,
            rule_id=rule.id,
            event_key=str(event_key),
            contact_id=contact.id,
            status='completed',
            detail='Tarefa criada.',
            config_snapshot={'assignee_id': rule.assignee_id, 'stop_on_reply': rule.stop_on_reply},
        )
        db.session.add(run)
        db.session.flush()
        if not assignee_available(rule):
            run.status, run.detail = 'skipped', 'O responsável perdeu acesso à conta. Atualize a regra.'
            continue
        if rule.actions:
            event_data = {
                'opportunity_id': opportunity_id,
                'trigger_event': event,
                'trigger_thread_id': (context or {}).get('thread_id'),
                'trigger_native_whatsapp': (context or {}).get('native_whatsapp', False),
                'task_title': (context or {}).get('task_title'),
                'booking_id': (context or {}).get('booking_id'),
                'stage_entry': str(event_key) if event == 'opportunity.stage_idle' else None,
                **{key: context[key] for key in ('inbound_channel', 'atlas_handoff') if context and key in context},
                **({'comment_id': context['comment_id']} if context and context.get('comment_id') else {}),
            }
            start = now()
            first = rule.actions[0]
            if first.get('stage_days'):
                start += timedelta(days=first['stage_days'])
            if 'booking_before_minutes' in first and event_data['booking_id']:
                booking = db.session.get(Booking, event_data['booking_id'])
                start = max(start, booking.starts_at - timedelta(minutes=first['booking_before_minutes']))
            schedule(run, rule.actions, 0, start, event_data)
            run.status, run.detail = 'queued', 'Etapas agendadas.'
        else:  # Backwards-compatible rules: existing immediate task behavior is preserved.
            task = Task(
                workspace_id=workspace_id,
                title=rule.task_title,
                contact_id=contact.id,
                opportunity_id=opportunity_id,
                **task_defaults(rule.assignee_id, context),
                due_date=now().astimezone(ZoneInfo(workspace.timezone)).date() + timedelta(days=rule.due_days),
            )
            db.session.add(task)
            db.session.flush()
            run.task_id = task.id
            log(workspace_id, 'automation_create_task', task, {'run_id': run.id})
        log(workspace_id, 'automation_run', run, {'event': event})


def stage_entry(deal):
    latest = (
        StageHistory.query.filter_by(workspace_id=deal.workspace_id, opportunity_id=deal.id)
        .order_by(StageHistory.created_at.desc(), StageHistory.id.desc())
        .first()
    )
    return latest.id if latest else deal.id


def sync_booking_jobs(booking, previous_start=None):
    jobs = (
        AutomationJob.query.filter(
            AutomationJob.workspace_id == booking.workspace_id,
            AutomationJob.action['booking_id'].as_string() == booking.id,
        )
        .order_by(AutomationJob.run_id, AutomationJob.position)
        .with_for_update()
        .all()
    )
    anchors = {job.run_id: job for job in jobs if job.position == 0}
    shifts = {}
    for job in jobs:
        if booking.status == 'cancelled':
            if job.status == 'pending':
                job.status, job.detail = 'cancelled', 'Agendamento cancelado.'
                run = db.session.get(AutomationRun, job.run_id)
                run.status, run.detail = 'cancelled', job.detail
            if job.status == 'completed' and job.action['kind'] == 'create_task' and job.result_id:
                task = (
                    Task.query.filter_by(workspace_id=booking.workspace_id, id=job.result_id).with_for_update().first()
                )
                if task and task.status in ('todo', 'doing'):
                    task.status = 'cancelled'
                    log(booking.workspace_id, 'automation_cancel_booking_task', task)
        elif previous_start and job.status == 'pending':
            anchor = anchors.get(job.run_id)
            if (
                anchor
                and anchor.status == 'pending'
                and 'booking_before_minutes' in anchor.action
                and not anchor.action.get('wait_started_at')
            ):
                if job.run_id not in shifts:
                    planned = max(now(), booking.starts_at - timedelta(minutes=anchor.action['booking_before_minutes']))
                    shifts[job.run_id] = (
                        planned + timedelta(minutes=anchor.action.get('delay_minutes', 0)) - anchor.scheduled_at
                    )
                job.scheduled_at += shifts[job.run_id]


def schedule(run, actions, position, start, event_data):
    """Queue one path of the flow. A branch is always its path's last step and carries both paths with it."""
    scheduled = start
    for offset, action in enumerate(actions):
        scheduled += timedelta(minutes=action.get('delay_minutes', 0))
        db.session.add(
            AutomationJob(
                workspace_id=run.workspace_id,
                run_id=run.id,
                position=position + offset,
                action={**action, **event_data},
                scheduled_at=scheduled,
            )
        )


def subject(action, workspace, *, lock_deal=False):
    """The deal and Instagram comment the event referred to, as conditions see them."""
    deal = None
    if action.get('opportunity_id'):
        query = Opportunity.query.filter_by(id=action['opportunity_id'], workspace_id=workspace.id)
        deal = (query.with_for_update().populate_existing() if lock_deal else query).first()
    comment = None
    if action.get('comment_id'):
        comment = InstagramComment.query.filter_by(comment_id=action['comment_id'], workspace_id=workspace.id).first()
    return deal, comment


def condition_context(comment, run, contact, action):
    """Event data conditions can test: the Instagram comment, and the contact's latest reply since the run began."""
    context = {'text': comment.text, 'media_id': comment.media_id} if comment else {}
    reply = (
        InboxMessage.query.join(InboxThread, InboxThread.id == InboxMessage.thread_id)
        .filter(
            InboxMessage.workspace_id == run.workspace_id,
            InboxThread.contact_id == contact.id,
            InboxMessage.direction == 'in',
            InboxMessage.created_at >= run.created_at,
        )
        .order_by(InboxMessage.created_at.desc())
        .first()
    )
    if action.get('task_title'):
        context['task_title'] = action['task_title']
    if reply:
        context['reply_text'] = reply.content
    return context


def reply_wait_path(job, run, contact):
    action = job.action
    if not action.get('wait_started_at'):
        thread_id = action.get('trigger_thread_id')
        native_whatsapp = action['reply_channel'] == 'whatsapp' and (
            not thread_id or action.get('trigger_native_whatsapp')
        )
        if (
            not thread_id
            and action.get('opportunity_id')
            and Opportunity.query.filter_by(workspace_id=run.workspace_id, contact_id=contact.id, status='open').count()
            > 1
        ):
            raise APIError('Há mais de um negócio aberto para esta conversa.', 422)
        candidates = []
        if native_whatsapp:
            conversations = WhatsAppConversation.query.filter_by(workspace_id=run.workspace_id, contact_id=contact.id)
            if thread_id:
                conversations = conversations.filter_by(id=thread_id)
            candidates = conversations.limit(2).all()
        if not candidates and not action.get('trigger_native_whatsapp'):
            native_whatsapp = False
            threads = InboxThread.query.filter_by(
                workspace_id=run.workspace_id, contact_id=contact.id, channel=action['reply_channel']
            )
            if thread_id:
                threads = threads.filter_by(id=thread_id)
            candidates = threads.limit(2).all()
        if len(candidates) != 1:
            raise APIError('Selecione um canal com uma única conversa vinculada.', 422)
        start = job.scheduled_at
        action = job.action = {
            **action,
            'wait_thread_id': candidates[0].id,
            'wait_native_whatsapp': native_whatsapp,
            'wait_started_at': start.isoformat(),
            'wait_deadline': (start + timedelta(minutes=action['wait_reply_minutes'])).isoformat(),
        }

    start = datetime.fromisoformat(action['wait_started_at'])
    deadline = datetime.fromisoformat(action['wait_deadline'])
    if action.get('wait_native_whatsapp'):
        reply = (
            WhatsAppMessage.query.filter_by(
                workspace_id=run.workspace_id, conversation_id=action['wait_thread_id'], direction='in'
            )
            .filter(
                WhatsAppMessage.created_at > start,
                WhatsAppMessage.created_at <= deadline,
                WhatsAppMessage.occurred_at >= start.replace(microsecond=0),
            )
            .first()
        )
    else:
        reply = (
            InboxMessage.query.filter_by(
                workspace_id=run.workspace_id, thread_id=action['wait_thread_id'], direction='in'
            )
            .filter(InboxMessage.created_at > start, InboxMessage.created_at <= deadline)
            .first()
        )
    if reply:
        return 'yes'
    if now() >= deadline:
        return 'no'
    job.scheduled_at = min(deadline, now() + timedelta(minutes=1))
    job.detail = 'Aguardando resposta na conversa vinculada.'
    return None


def follow_branch(job, run, contact, workspace):
    """Evaluate the branch now, against the contact as it is, and queue only the chosen path."""
    action = job.action
    deal, comment = subject(action, workspace)
    if action.get('wait_reply_minutes'):
        path = reply_wait_path(job, run, contact)
        if path is None:
            return None
    else:
        path = (
            'yes'
            if matches(action.get('conditions', {}), contact, deal, condition_context(comment, run, contact, action))
            else 'no'
        )
    event_data = {
        key: action[key]
        for key in (
            'opportunity_id',
            'comment_id',
            'trigger_event',
            'inbound_channel',
            'atlas_handoff',
            'trigger_thread_id',
            'trigger_native_whatsapp',
            'task_title',
            'booking_id',
        )
        if key in action
    }
    schedule(run, action.get(path) or [], job.position + 1, now(), event_data)
    log(workspace.id, 'automation_branch', run, {'job_id': job.id, 'path': path})
    return path


def execute(job, rule, run, contact, workspace):
    action = job.action
    deal, comment = subject(action, workspace, lock_deal=action['kind'] == 'move_stage')
    if not matches(action.get('conditions', {}), contact, deal, condition_context(comment, run, contact, action)):
        return None
    assignee_id = rule.assignee_id
    if action.get('assign_deal_owner'):
        owner_id = deal.owner_id if deal else None
        if owner_id and owner_id in {user.id for user in account_users(workspace.id) if user.active}:
            assignee_id = owner_id
    if action['kind'] == 'atlas_assign':
        from .atlas_automations import queue

        return queue(job, run, contact, workspace, deal)
    if action['kind'] in ('reply_comment', 'private_reply'):
        from .instagram import comment_action

        return comment_action(
            action['kind'],
            comment,
            contact,
            action.get('content', ''),
            workspace,
            action.get('buttons'),
            action.get('quick_replies'),
        )
    if action['kind'] == 'instagram_message':
        from .instagram import automation_message

        return automation_message(
            contact,
            action.get('content', ''),
            workspace,
            'automation:' + job.id,
            action.get('buttons'),
            action.get('quick_replies'),
        )
    if action['kind'] == 'send_message':
        from .communications import enqueue, render

        template = MessageTemplate.query.filter_by(id=action.get('template_id'), workspace_id=workspace.id).first()
        if not template:
            raise APIError('Modelo indisponível nesta conta.', 422)
        result = enqueue(
            workspace.id,
            contact,
            template.channel,
            render(template.content, contact),
            render(template.subject, contact),
            'automation:' + job.id,
        )
    elif action['kind'] == 'add_tag':
        tag = action['tag'].strip()
        if tag not in (contact.tags or []):
            contact.tags = [*(contact.tags or []), tag]
        log(workspace.id, 'automation_add_tag', contact, {'run_id': run.id, 'tag': tag})
        return contact.id
    elif action['kind'] == 'move_stage':
        stage = PipelineStage.query.filter_by(id=action.get('stage_id'), workspace_id=workspace.id).first()
        if not stage:
            raise APIError('Etapa indisponível nesta conta.', 422)
        if not deal or deal.status != 'open':
            return None  # Nothing to move: the step is dismissed rather than failed.
        if deal.stage_id != stage.id:
            history = StageHistory(
                workspace_id=workspace.id,
                opportunity_id=deal.id,
                from_stage_id=deal.stage_id,
                to_stage_id=stage.id,
                user_id=rule.assignee_id
                or deal.owner_id
                or next(u.id for u in account_users(workspace.id) if u.active),
            )
            db.session.add(history)
            deal.stage_id = stage.id
            db.session.flush()
            if action.get('trigger_event') != 'opportunity.stage_idle':
                emit(workspace.id, 'opportunity.stage_idle', history.id, contact, deal.id)
        log(workspace.id, 'automation_move_stage', deal, {'run_id': run.id, 'stage_id': stage.id})
        return deal.id
    elif action['kind'] == 'follow_up':
        result = Activity(
            workspace_id=workspace.id,
            contact_id=contact.id,
            opportunity_id=action.get('opportunity_id'),
            owner_id=assignee_id,
            title=action['title'],
            kind='follow_up',
            scheduled_at=job.scheduled_at + timedelta(days=action.get('due_days', 0)),
        )
        db.session.add(result)
        db.session.flush()
        log(workspace.id, 'automation_create_followup', result, {'run_id': run.id})
    else:
        result = Task(
            workspace_id=workspace.id,
            contact_id=contact.id,
            opportunity_id=action.get('opportunity_id'),
            **task_defaults(assignee_id, action),
            title=action['title'],
            due_date=now().astimezone(ZoneInfo(workspace.timezone)).date() + timedelta(days=action.get('due_days', 0)),
        )
        db.session.add(result)
        db.session.flush()
        if not run.task_id:
            run.task_id = result.id
        log(workspace.id, 'automation_create_task', result, {'run_id': run.id})
    return result.id


def process(workspace_id=None, limit=50):
    processed = []
    for _ in range(limit):
        q = AutomationJob.query.filter(AutomationJob.status == 'pending', AutomationJob.scheduled_at <= now())
        if workspace_id:
            q = q.filter_by(workspace_id=workspace_id)
        earlier = aliased(AutomationJob)
        q = q.filter(
            ~db.exists().where(
                earlier.run_id == AutomationJob.run_id,
                earlier.position < AutomationJob.position,
                earlier.status == 'pending',
            )
        )
        job = (
            q.order_by(AutomationJob.scheduled_at, AutomationJob.run_id, AutomationJob.position)
            .with_for_update(skip_locked=True)
            .first()
        )
        if not job:
            break
        run = db.session.get(AutomationRun, job.run_id)
        rule = AutomationRule.query.filter_by(id=run.rule_id, workspace_id=job.workspace_id).first()
        live_active = bool(rule and rule.active)
        if rule and run.config_snapshot:
            rule = SimpleNamespace(**{**rule.to_dict(), **run.config_snapshot})
        workspace = db.session.get(Workspace, job.workspace_id)
        contact = Contact.query.filter_by(id=run.contact_id, workspace_id=job.workspace_id, archived=False).first()
        previous = AutomationJob.query.filter(
            AutomationJob.run_id == run.id,
            AutomationJob.position < job.position,
            db.or_(AutomationJob.status != 'completed', AutomationJob.scheduled_at > job.scheduled_at),
        ).first()
        if (
            not rule
            or not live_active
            or not workspace
            or not workspace.active
            or not contact
            or not assignee_available(rule)
            or previous
        ):
            job.status, job.detail = 'skipped', 'Regra pausada, etapa anterior não concluída ou acesso indisponível.'
        else:
            try:
                with db.session.begin_nested():
                    booking_id = job.action.get('booking_id')
                    booking = (
                        Booking.query.filter_by(workspace_id=job.workspace_id, id=booking_id).first()
                        if booking_id
                        else None
                    )
                    entry = job.action.get('stage_entry') if job.position == 0 else None
                    deal, _ = subject(job.action, workspace, lock_deal=True) if entry else (None, None)
                    if booking_id and (not booking or booking.status != 'confirmed'):
                        job.status, job.detail = 'cancelled', 'Agendamento cancelado ou indisponível.'
                    elif entry and (not deal or deal.status != 'open' or stage_entry(deal) != entry):
                        job.status, job.detail = 'skipped', 'O negócio saiu da etapa ou foi encerrado.'
                    elif job.action.get('kind') == 'branch':
                        path = follow_branch(job, run, contact, workspace)
                        if path is not None:
                            job.status = 'completed'
                            if job.action.get('wait_reply_minutes'):
                                job.detail = 'Resposta recebida.' if path == 'yes' else 'Prazo venceu sem resposta.'
                            else:
                                job.detail = (
                                    'Condição atendida; caminho Sim.'
                                    if path == 'yes'
                                    else 'Condição não atendida; caminho Não.'
                                )
                    else:
                        job.result_id = execute(job, rule, run, contact, workspace)
                        job.status, job.detail = (
                            'completed',
                            job.detail
                            or ('Ação concluída.' if job.result_id else 'Condição não atendida; etapa dispensada.'),
                        )
            except Exception as error:  # action boundary: one failed step must not stop the queue
                current_app.logger.warning('Falha na etapa %s: %s', job.id, type(error).__name__)
                job.status = 'failed'
                job.detail = (
                    error.message
                    if isinstance(error, APIError) and job.action.get('wait_reply_minutes')
                    else 'Ação não concluída. Confira o contato, modelo e responsável.'
                )
        db.session.flush()
        statuses = {item.status for item in AutomationJob.query.filter_by(run_id=run.id)}
        priority = ('pending', 'failed', 'cancelled', 'skipped')
        status = next((value for value in priority if value in statuses), 'completed')
        run.status = 'queued' if status == 'pending' else status
        run.detail = 'Etapas agendadas.' if run.status == 'queued' else 'Processamento encerrado; confira as etapas.'
        if job.status != 'pending':
            log(job.workspace_id, 'automation_job', job, {'status': job.status})
        db.session.commit()
        processed.append(job.to_dict())
    return processed


def received_reply(workspace_id, contact, event_key, *, whatsapp_message=None, instagram_supported=False):
    """Cancel only future actions; completed tasks and historical messages stay intact."""

    runs = AutomationRun.query.filter_by(workspace_id=workspace_id, contact_id=contact.id).all()
    for run in runs:
        rule = AutomationRule.query.filter_by(id=run.rule_id, workspace_id=workspace_id).first()
        stop = run.config_snapshot.get('stop_on_reply', rule.stop_on_reply if rule else False)
        if not stop:
            continue
        changed = False
        for job in AutomationJob.query.filter_by(workspace_id=workspace_id, run_id=run.id).all():
            if job.status == 'pending':
                job.status, job.detail = 'cancelled', 'Contato respondeu; retorno automático interrompido.'
                changed = True
            for message in (
                InboxMessage.query.filter_by(workspace_id=workspace_id, idempotency_key='automation:' + job.id)
                .filter(InboxMessage.status.in_(['queued', 'blocked']))
                .all()
            ):
                message.status, message.error = 'cancelled', 'Contato respondeu.'
                changed = True
        if changed:
            run.status, run.detail = 'cancelled', 'Contato respondeu; ações futuras canceladas.'
            log(workspace_id, 'automation_stopped_on_reply', run)
    message = whatsapp_message or InboxMessage.query.filter_by(id=str(event_key), workspace_id=workspace_id).first()
    context = {'reply_text': message.content} if message else {}
    if whatsapp_message:
        context.update(inbound_channel='whatsapp', thread_id=whatsapp_message.conversation_id, native_whatsapp=True)
    elif message:
        context['thread_id'] = message.thread_id
    if instagram_supported:
        context['inbound_channel'] = 'instagram'
    emit(
        workspace_id,
        'message.received',
        event_key,
        contact,
        context=context,
    )
