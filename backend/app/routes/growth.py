from flask import Blueprint, g, request
from marshmallow import fields as f, validate, ValidationError, pre_load
from sqlalchemy import func
import hashlib
from sqlalchemy.exc import IntegrityError
from ..extensions import db, limiter
from ..models import LeadForm, FormSubmission, Contact, Opportunity, PipelineStage, AutomationRule, AutomationRun, Workspace, MessageTemplate, AutomationJob
from ..schemas import StrictSchema, text, ref, choice
from ..common import require, query, get, add, update, commit, page, payload, user_ref, APIError
from ..services.conditions import ConditionsSchema
from ..services.automations import emit
from ..services.form_fields import FormFieldSchema, validate_definitions, parse_answers

bp = Blueprint('growth', __name__)
CONSENT = 'Autorizo o contato em resposta a esta solicitação.'


class FormSchema(StrictSchema):
    fields = f.List(f.Nested(FormFieldSchema), validate=validate.Length(max=30))
    brand_name = f.String(validate=validate.Length(max=120))
    accent_color = f.String(validate=validate.Regexp(r"^#[0-9a-fA-F]{6}$"))
    name = text(150, required=True)
    headline = text(180, required=True)
    description = f.String(validate=validate.Length(max=2000))
    success_message = text(500)
    stage_id = ref(required=True)
    source = text(100)
    active = f.Boolean()

    @pre_load
    def clear_description(self, data, **kwargs):
        # The shared editor sends null when an optional field is cleared.
        if isinstance(data, dict) and data.get('description', '') is None:
            return {**data, 'description': ''}
        return data


class SubmissionSchema(StrictSchema):
    answers = f.Dict(keys=f.String(), values=f.Raw(), load_default=dict, validate=validate.Length(max=30))
    attribution = f.Dict(keys=f.String(validate=validate.OneOf(["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"])), values=f.String(validate=validate.Length(max=300)), load_default=dict)
    submission_key = ref(required=True)
    name = text(180, required=True)
    email = f.Email(required=True, validate=validate.Length(max=254))
    phone = f.String(validate=validate.Length(max=30), load_default='')
    consent = f.Boolean(required=True, validate=validate.Equal(True))
    website = f.String(validate=validate.Length(max=0), load_default='')  # Honeypot, not the lead's website.

    @pre_load
    def normalize_email(self, data, **kwargs):
        if isinstance(data, dict) and isinstance(data.get('email'), str):
            return {**data, 'email': data['email'].strip().lower()}
        return data


class ActionSchema(StrictSchema):
    conditions = f.Nested(ConditionsSchema)
    kind = choice('create_task send_message follow_up add_tag move_stage reply_comment private_reply', required=True)
    title = text(180)
    content = text(1000)
    template_id = ref()
    tag = text(80)
    stage_id = ref()
    delay_minutes = f.Integer(validate=validate.Range(min=0, max=525600), load_default=0)
    due_days = f.Integer(validate=validate.Range(min=0, max=365), load_default=0)


class RuleSchema(StrictSchema):
    conditions = f.Nested(ConditionsSchema)
    stop_on_reply = f.Boolean()
    required_tag = text(80, allow_none=True)
    actions = f.List(f.Nested(ActionSchema), validate=validate.Length(max=10))
    name = text(150, required=True)
    event = choice('contact.created form.submitted message.received booking.created booking.cancelled opportunity.created instagram.comment opportunity.stage_changed opportunity.won opportunity.lost', required=True)
    source = text(100, allow_none=True)
    task_title = text(180, required=True)
    due_days = f.Integer(validate=validate.Range(min=0, max=365))
    assignee_id = ref(nullable=True)
    active = f.Boolean()


@bp.get('/forms')
@require()
def forms():
    return page(query(LeadForm).order_by(LeadForm.created_at.desc()))


@bp.post('/forms')
@require('owner', 'admin')
def form_create():
    data = payload(FormSchema)
    validate_definitions(data.get('fields', []))
    get(PipelineStage, data['stage_id'])
    return commit(add(LeadForm, data), 201)


@bp.patch('/forms/<uuid:form_id>')
@require('owner', 'admin')
def form_update(form_id):
    row = get(LeadForm, form_id)
    data = payload(FormSchema, partial=True)
    if 'fields' in data: validate_definitions(data['fields'])
    if data.get('stage_id'):
        get(PipelineStage, data['stage_id'])
    update(row, data)
    return commit(row)


@bp.get('/forms/<uuid:form_id>/submissions')
@require()
def submissions(form_id):
    row = get(LeadForm, form_id)
    return page(query(FormSubmission).filter_by(form_id=row.id).order_by(FormSubmission.created_at.desc()))


def published_form(form_id):
    row = LeadForm.query.join(Workspace, LeadForm.workspace_id == Workspace.id).filter(
        LeadForm.id == str(form_id), LeadForm.active.is_(True), Workspace.active.is_(True)).first()
    if not row:
        raise APIError('Formulário indisponível.', 404)
    if not PipelineStage.query.filter_by(id=row.stage_id, workspace_id=row.workspace_id).first():
        raise APIError('Formulário indisponível.', 404)
    return row


@bp.get('/public/forms/<uuid:form_id>')
@limiter.limit('60 per minute')
def public_form(form_id):
    row = published_form(form_id)
    return {'headline': row.headline, 'description': row.description, 'consent_text': CONSENT,
            'fields': [{k: v for k, v in field.items() if k != 'map_to'} for field in row.fields],
            'brand_name': row.brand_name, 'accent_color': row.accent_color}


@bp.post('/public/forms/<uuid:form_id>/submit')
@limiter.limit('10 per minute; 100 per hour')
def public_submit(form_id):
    row = published_form(form_id)
    if request.content_length and request.content_length > 8192:
        raise APIError('Solicitação muito grande.', 413)
    data = payload(SubmissionSchema)
    email = data['email']
    if db.session.get_bind().dialect.name == 'postgresql':
        # Serialize capture of the same address across forms in this account.
        # The lock is released with the transaction, including rollback.
        lock_key = int.from_bytes(hashlib.sha256(f'{row.workspace_id}:{email}'.encode()).digest()[:8], 'big', signed=True)
        db.session.execute(db.text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_key})
    existing = FormSubmission.query.filter_by(form_id=row.id, submission_key=data['submission_key']).first()
    if existing:
        return {'message': row.success_message}, 200
    answers, mapped = parse_answers(row.fields, data['answers'])
    contact = (Contact.query.filter_by(workspace_id=row.workspace_id, archived=False)
               .filter(func.lower(func.trim(Contact.email)) == email)
               .order_by(Contact.created_at, Contact.id).first())
    created = contact is None
    if created:
        contact = Contact(workspace_id=row.workspace_id, name=data['name'].strip(), email=email,
                          phone=data['phone'].strip() or None, source=row.source)
        db.session.add(contact); db.session.flush()
    if mapped:
        contact.custom_fields = {**(contact.custom_fields or {}), **mapped}
    opportunity = Opportunity(workspace_id=row.workspace_id, contact_id=contact.id,
                              stage_id=row.stage_id, title=f"{row.name}: {data['name'].strip()}"[:180])
    db.session.add(opportunity); db.session.flush()
    submission = FormSubmission(workspace_id=row.workspace_id, form_id=row.id, submission_key=data['submission_key'],
                                contact_id=contact.id, opportunity_id=opportunity.id, consent_text=CONSENT,
                                answers={'name': data['name'].strip(), 'email': email, 'phone': data['phone'].strip(), **answers}, attribution=data['attribution'])
    db.session.add(submission)
    try:
        db.session.flush()  # Claim this submission key before dispatching actions.
        if created:
            emit(row.workspace_id, 'contact.created', contact.id, contact, opportunity.id)
        emit(row.workspace_id, 'opportunity.created', opportunity.id, contact, opportunity.id, source=row.source)
        emit(row.workspace_id, 'form.submitted', submission.id, contact, opportunity.id, source=row.source)
        from ..models import AuditLog
        db.session.add(AuditLog(workspace_id=row.workspace_id, action='public_form_submit', resource='form_submissions', resource_id=submission.id, details={'form_id': row.id}))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if not FormSubmission.query.filter_by(form_id=str(form_id), submission_key=data['submission_key']).first():
            raise
    # Never return contact details, identifiers or whether an email already existed.
    return {'message': row.success_message}, 200


@bp.get('/automations')
@require()
def rules():
    result = page(query(AutomationRule).order_by(AutomationRule.created_at.desc()))
    ids = [row['id'] for row in result['items']]
    stats = {}
    if ids:
        for rule_id, status, count, last in (query(AutomationRun).filter(AutomationRun.rule_id.in_(ids))
                .with_entities(AutomationRun.rule_id, AutomationRun.status, func.count(AutomationRun.id), func.max(AutomationRun.created_at))
                .group_by(AutomationRun.rule_id, AutomationRun.status).all()):
            item = stats.setdefault(rule_id, {'runs': 0, 'failed': 0, 'last_run_at': None})
            item['runs'] += count
            item['failed'] += count if status == 'failed' else 0
            if last and (not item['last_run_at'] or last.isoformat() > item['last_run_at']):
                item['last_run_at'] = last.isoformat()
    for row in result['items']:
        row['stats'] = stats.get(row['id'], {'runs': 0, 'failed': 0, 'last_run_at': None})
    return result


@bp.post('/automations')
@require('owner', 'admin')
def rule_create():
    data = payload(RuleSchema)
    validate_rule(data)
    return commit(add(AutomationRule, data), 201)


@bp.patch('/automations/<uuid:rule_id>')
@require('owner', 'admin')
def rule_update(rule_id):
    row = get(AutomationRule, rule_id)
    data = payload(RuleSchema, partial=True)
    validate_rule(data)
    update(row, data)
    return commit(row)


@bp.delete('/automations/<uuid:rule_id>')
@require('owner', 'admin')
def rule_delete(rule_id):
    row = get(AutomationRule, rule_id)
    if query(AutomationRun).filter_by(rule_id=row.id).first():
        raise APIError('Esta automação já foi executada e mantém histórico. Pause-a em vez de excluir.', 409)
    db.session.delete(row)
    db.session.commit()
    return '', 204


@bp.get('/automations/runs')
@require()
def runs():
    q = query(AutomationRun)
    for field in ('status', 'rule_id'):
        if request.args.get(field):
            q = q.filter(getattr(AutomationRun, field) == request.args[field])
    result = page(q.order_by(AutomationRun.created_at.desc()))
    names = {c.id: c.name for c in query(Contact).filter(Contact.id.in_([r['contact_id'] for r in result['items']])).all()} if result['items'] else {}
    for row in result['items']:
        row['contact_name'] = names.get(row['contact_id'])
    return result


@bp.post('/automations/runs/<uuid:run_id>/cancel')
@require('owner', 'admin')
def run_cancel(run_id):
    run = get(AutomationRun, run_id, lock=True)
    pending = query(AutomationJob).filter_by(run_id=run.id, status='pending').all()
    if not pending:
        raise APIError('Esta execução não tem etapas pendentes.', 409)
    for job in pending:
        job.status, job.detail = 'cancelled', 'Cancelada manualmente.'
    run.status, run.detail = 'cancelled', 'Cancelada manualmente.'
    db.session.commit()
    return run.to_dict()


# Keep each template lookup within the selected account, including nested workflow actions.
def validate_rule(data):
    user_ref(data.get('assignee_id'))
    for index, action in enumerate(data.get('actions', [])):
        action = ActionSchema().load(action)
        data['actions'][index] = action
        if action['kind'] == 'send_message':
            if not action.get('template_id'):
                raise APIError('Selecione um modelo para enviar a mensagem.', 422)
            action['template_id'] = str(action['template_id'])
            get(MessageTemplate, action['template_id'])
        elif action['kind'] in ('reply_comment', 'private_reply'):
            if not (action.get('content') or '').strip():
                raise APIError('Escreva o texto da resposta.', 422)
            if len(action['content'].encode()) > 1000:
                raise APIError('A resposta aceita até 1.000 bytes.', 422)
        elif action['kind'] == 'add_tag':
            if not action.get('tag'):
                raise APIError('Informe a tag que será adicionada.', 422)
        elif action['kind'] == 'move_stage':
            if not action.get('stage_id'):
                raise APIError('Selecione a etapa de destino.', 422)
            action['stage_id'] = str(action['stage_id'])
            get(PipelineStage, action['stage_id'])
        elif not action.get('title'):
            raise APIError('Informe o título da tarefa ou retorno.', 422)


@bp.get('/automations/jobs')
@require()
def jobs():
    q = query(AutomationJob)
    if request.args.get('status'):
        q = q.filter(AutomationJob.status == request.args['status'])
    result = page(q.order_by(AutomationJob.scheduled_at.desc()))
    run_ids = [row['run_id'] for row in result['items']]
    if run_ids:
        runs_by_id = {r.id: r for r in query(AutomationRun).filter(AutomationRun.id.in_(run_ids)).all()}
        contacts = {c.id: c.name for c in query(Contact).filter(Contact.id.in_([r.contact_id for r in runs_by_id.values()])).all()}
        for row in result['items']:
            run = runs_by_id.get(row['run_id'])
            row['rule_id'] = run.rule_id if run else None
            row['contact_name'] = contacts.get(run.contact_id) if run else None
    return result


@bp.post('/automations/jobs/<uuid:job_id>/cancel')
@require('owner', 'admin')
def job_cancel(job_id):
    job = get(AutomationJob, job_id, lock=True)
    if job.status != 'pending':
        raise APIError('Somente etapas pendentes podem ser canceladas.', 409)
    job.status, job.detail = 'cancelled', 'Cancelada manualmente.'
    db.session.commit()
    return job.to_dict()


@bp.post('/automations/jobs/<uuid:job_id>/retry')
@require('owner', 'admin')
def job_retry(job_id):
    from ..models import now
    job = get(AutomationJob, job_id, lock=True)
    if job.status not in ('failed', 'skipped'):
        raise APIError('Somente etapas que falharam ou foram ignoradas podem ser reprocessadas.', 409)
    job.status, job.detail, job.scheduled_at = 'pending', 'Reprocessamento solicitado.', now()
    run = db.session.get(AutomationRun, job.run_id)
    run.status, run.detail = 'queued', 'Etapas agendadas.'
    db.session.commit()
    return job.to_dict()


@bp.post('/automations/process')
@require('owner', 'admin')
def process_jobs():
    from ..services.automations import process
    return {'items': process(g.workspace_id, limit=50)}
