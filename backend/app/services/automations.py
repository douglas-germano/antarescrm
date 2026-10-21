"""Account-scoped workflow execution. Database actions are atomic; outbound I/O uses the outbox."""
from datetime import timedelta
from types import SimpleNamespace
from .conditions import matches
from zoneinfo import ZoneInfo
from sqlalchemy.orm import aliased
from ..extensions import db
from ..models import Workspace, AutomationRule, AutomationRun, AutomationJob, Task, Activity, Contact, MessageTemplate, AuditLog, Opportunity, now
from ..access import account_users
from ..common import APIError


def assignee_available(rule):
    return not rule.assignee_id or rule.assignee_id in {u.id for u in account_users(rule.workspace_id) if u.active}


def log(workspace_id, action, row, details=None):
    db.session.add(AuditLog(workspace_id=workspace_id, action=action, resource=row.__tablename__, resource_id=row.id, details=details or {}))


def emit(workspace_id, event, event_key, contact, opportunity_id=None, source=None, context=None):
    """`context` carries event data for conditions (e.g. the Instagram comment text) and is never stored in rules."""
    workspace = db.session.get(Workspace, workspace_id)
    if not workspace or not workspace.active or contact.workspace_id != workspace_id:
        return
    deal = Opportunity.query.filter_by(id=opportunity_id, workspace_id=workspace_id).first() if opportunity_id else None
    rules = AutomationRule.query.filter_by(workspace_id=workspace_id, event=event, active=True).all()
    for rule in rules:
        if rule.source and rule.source.casefold() != (source or contact.source or '').casefold():
            continue
        if not matches(rule.conditions, contact, deal, context): continue
        if rule.required_tag and rule.required_tag not in (contact.tags or []):
            continue
        if AutomationRun.query.filter_by(rule_id=rule.id, event_key=str(event_key)).first():
            continue
        run = AutomationRun(workspace_id=workspace_id, rule_id=rule.id, event_key=str(event_key),
                            contact_id=contact.id, status='completed', detail='Tarefa criada.',
                            config_snapshot={'assignee_id': rule.assignee_id, 'stop_on_reply': rule.stop_on_reply})
        db.session.add(run); db.session.flush()
        if not assignee_available(rule):
            run.status, run.detail = 'skipped', 'O responsável perdeu acesso à conta. Atualize a regra.'
            continue
        if rule.actions:
            scheduled = now()
            for position, action in enumerate(rule.actions):
                scheduled += timedelta(minutes=action.get('delay_minutes', 0))
                db.session.add(AutomationJob(workspace_id=workspace_id, run_id=run.id, position=position,
                    action={**action, 'opportunity_id': opportunity_id, **({'comment_id': context['comment_id']} if context and context.get('comment_id') else {})}, scheduled_at=scheduled))
            run.status, run.detail = 'queued', 'Etapas agendadas.'
        else:  # Backwards-compatible rules: existing immediate task behavior is preserved.
            task = Task(workspace_id=workspace_id, title=rule.task_title, contact_id=contact.id,
                        opportunity_id=opportunity_id, assignee_id=rule.assignee_id,
                        due_date=now().astimezone(ZoneInfo(workspace.timezone)).date() + timedelta(days=rule.due_days))
            db.session.add(task); db.session.flush(); run.task_id = task.id
            log(workspace_id, 'automation_create_task', task, {'run_id': run.id})
        log(workspace_id, 'automation_run', run, {'event': event})


def execute(job, rule, run, contact, workspace):
    action = job.action
    deal = Opportunity.query.filter_by(id=action.get('opportunity_id'), workspace_id=workspace.id).first() if action.get('opportunity_id') else None
    comment = None
    if action.get('comment_id'):
        from ..models import InstagramComment
        comment = InstagramComment.query.filter_by(comment_id=action['comment_id'], workspace_id=workspace.id).first()
    if not matches(action.get('conditions', {}), contact, deal, {'text': comment.text, 'media_id': comment.media_id} if comment else None):
        return None
    if action['kind'] in ('reply_comment', 'private_reply'):
        from .instagram import comment_action
        return comment_action(action['kind'], comment, contact, action.get('content', ''), workspace)
    if action['kind'] == 'send_message':
        from .communications import enqueue, render
        template = MessageTemplate.query.filter_by(id=action.get('template_id'), workspace_id=workspace.id).first()
        if not template: raise APIError('Modelo indisponível nesta conta.', 422)
        result = enqueue(workspace.id, contact, template.channel, render(template.content, contact),
                         render(template.subject, contact), 'automation:' + job.id)
    elif action['kind'] == 'add_tag':
        tag = action['tag'].strip()
        if tag not in (contact.tags or []):
            contact.tags = [*(contact.tags or []), tag]
        log(workspace.id, 'automation_add_tag', contact, {'run_id': run.id, 'tag': tag})
        return contact.id
    elif action['kind'] == 'move_stage':
        from ..models import PipelineStage, StageHistory
        stage = PipelineStage.query.filter_by(id=action.get('stage_id'), workspace_id=workspace.id).first()
        if not stage: raise APIError('Etapa indisponível nesta conta.', 422)
        if not deal or deal.status != 'open':
            return None  # Nothing to move: the step is dismissed rather than failed.
        if deal.stage_id != stage.id:
            db.session.add(StageHistory(workspace_id=workspace.id, opportunity_id=deal.id, from_stage_id=deal.stage_id, to_stage_id=stage.id, user_id=rule.assignee_id or deal.owner_id or next(u.id for u in account_users(workspace.id) if u.active)))
            deal.stage_id = stage.id
        log(workspace.id, 'automation_move_stage', deal, {'run_id': run.id, 'stage_id': stage.id})
        return deal.id
    elif action['kind'] == 'follow_up':
        result = Activity(workspace_id=workspace.id, contact_id=contact.id, opportunity_id=action.get('opportunity_id'),
            owner_id=rule.assignee_id, title=action['title'], kind='follow_up', scheduled_at=job.scheduled_at + timedelta(days=action.get('due_days', 0)))
        db.session.add(result); db.session.flush()
        log(workspace.id, 'automation_create_followup', result, {'run_id': run.id})
    else:
        result = Task(workspace_id=workspace.id, contact_id=contact.id, opportunity_id=action.get('opportunity_id'),
            assignee_id=rule.assignee_id, title=action['title'],
            due_date=now().astimezone(ZoneInfo(workspace.timezone)).date() + timedelta(days=action.get('due_days', 0)))
        db.session.add(result); db.session.flush()
        if not run.task_id: run.task_id = result.id
        log(workspace.id, 'automation_create_task', result, {'run_id': run.id})
    return result.id


def process(workspace_id=None, limit=50):
    processed = []
    for _ in range(limit):
        q = AutomationJob.query.filter(AutomationJob.status == 'pending', AutomationJob.scheduled_at <= now())
        if workspace_id: q = q.filter_by(workspace_id=workspace_id)
        earlier = aliased(AutomationJob)
        q = q.filter(~db.exists().where(earlier.run_id == AutomationJob.run_id, earlier.position < AutomationJob.position, earlier.status == 'pending'))
        job = q.order_by(AutomationJob.scheduled_at, AutomationJob.run_id, AutomationJob.position).with_for_update(skip_locked=True).first()
        if not job: break
        run = db.session.get(AutomationRun, job.run_id)
        rule = AutomationRule.query.filter_by(id=run.rule_id, workspace_id=job.workspace_id).first()
        live_active = bool(rule and rule.active)
        if rule and run.config_snapshot:
            rule = SimpleNamespace(**{**rule.to_dict(), **run.config_snapshot})
        workspace = db.session.get(Workspace, job.workspace_id)
        contact = Contact.query.filter_by(id=run.contact_id, workspace_id=job.workspace_id, archived=False).first()
        previous = AutomationJob.query.filter(AutomationJob.run_id == run.id, AutomationJob.position < job.position, db.or_(AutomationJob.status != 'completed', AutomationJob.scheduled_at > job.scheduled_at)).first()
        if not rule or not live_active or not workspace or not workspace.active or not contact or not assignee_available(rule) or previous:
            job.status, job.detail = 'skipped', 'Regra pausada, etapa anterior não concluída ou acesso indisponível.'
        else:
            try:
                with db.session.begin_nested():
                    job.result_id = execute(job, rule, run, contact, workspace)
                    job.status, job.detail = 'completed', ('Ação concluída.' if job.result_id else 'Condição não atendida; etapa dispensada.')
            except Exception:
                job.status, job.detail = 'failed', 'Ação não concluída. Confira o contato, modelo e responsável.'
        db.session.flush()
        siblings = AutomationJob.query.filter_by(run_id=run.id).all()
        run.status = 'queued' if any(item.status == 'pending' for item in siblings) else ('failed' if any(item.status == 'failed' for item in siblings) else ('skipped' if any(item.status == 'skipped' for item in siblings) else 'completed'))
        run.detail = 'Etapas agendadas.' if run.status == 'queued' else 'Processamento encerrado; confira as etapas.'
        log(job.workspace_id, 'automation_job', job, {'status': job.status})
        db.session.commit(); processed.append(job.to_dict())
    return processed


def received_reply(workspace_id, contact, event_key):
    """Cancel only future actions; completed tasks and historical messages stay intact."""
    from ..models import InboxMessage, InboxThread
    runs = AutomationRun.query.filter_by(workspace_id=workspace_id, contact_id=contact.id).all()
    for run in runs:
        rule = AutomationRule.query.filter_by(id=run.rule_id, workspace_id=workspace_id).first()
        stop = run.config_snapshot.get('stop_on_reply', rule.stop_on_reply if rule else False)
        if not stop: continue
        changed = False
        for job in AutomationJob.query.filter_by(workspace_id=workspace_id, run_id=run.id).all():
            if job.status == 'pending':
                job.status, job.detail = 'cancelled', 'Contato respondeu; retorno automático interrompido.'
                changed = True
            for message in InboxMessage.query.filter_by(workspace_id=workspace_id, idempotency_key='automation:' + job.id).filter(InboxMessage.status.in_(['queued', 'blocked'])).all():
                message.status, message.error = 'cancelled', 'Contato respondeu.'
                changed = True
        if changed:
            run.status, run.detail = 'cancelled', 'Contato respondeu; ações futuras canceladas.'
            log(workspace_id, 'automation_stopped_on_reply', run)
    emit(workspace_id, 'message.received', event_key, contact)
