"""Public lead-form submissions: contact, opportunity and submission records plus automation events."""

import hashlib

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ..common import APIError
from ..extensions import db
from ..models import AuditLog, Contact, FormSubmission, LeadForm, Opportunity, PipelineStage, Workspace
from ..schemas.growth import CONSENT
from .automations import emit
from .domains import ensure_scope
from .form_design import merged_design, phone_required
from .form_fields import parse_answers
from .funnels import record_conversion


def published_form(form_id):
    row = (
        LeadForm.query.join(Workspace, LeadForm.workspace_id == Workspace.id)
        .filter(LeadForm.id == str(form_id), LeadForm.active.is_(True), Workspace.active.is_(True))
        .first()
    )
    if not row or not PipelineStage.query.filter_by(id=row.stage_id, workspace_id=row.workspace_id).first():
        raise APIError('Formulário indisponível.', 404)
    ensure_scope(row.workspace_id)
    return row


def consent_text(row):
    return (row.settings or {}).get('consent_text') or CONSENT


def after_submit(row):
    return {'type': 'message', 'url': '', **((row.settings or {}).get('after_submit') or {})}


def public_payload(row):
    """Everything a visitor needs to render the form; CRM mappings stay private."""
    return {
        'id': row.id,
        'headline': row.headline,
        'description': row.description,
        'consent_text': consent_text(row),
        'fields': [{k: v for k, v in field.items() if k != 'map_to'} for field in row.fields],
        'brand_name': row.brand_name,
        'accent_color': row.accent_color,
        'design': merged_design(row.design),
        'base_fields': (row.settings or {}).get('base_fields') or {},
    }


def submit(row, data):
    """Store one submission of the published form `row`; repeating a submission_key is a no-op."""
    email = data['email']
    if phone_required(row.settings) and not data['phone'].strip():
        raise APIError('Informe o telefone.', 422)
    if db.session.get_bind().dialect.name == 'postgresql':
        # Serialize capture of the same address across forms in this account.
        # The lock is released with the transaction, including rollback.
        lock_key = int.from_bytes(
            hashlib.sha256(f'{row.workspace_id}:{email}'.encode()).digest()[:8], 'big', signed=True
        )
        db.session.execute(db.text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_key})
    existing = FormSubmission.query.filter_by(form_id=row.id, submission_key=data['submission_key']).first()
    if existing:
        return
    answers, mapped = parse_answers(row.fields, data['answers'])
    contact = (
        Contact.query.filter_by(workspace_id=row.workspace_id, archived=False)
        .filter(func.lower(func.trim(Contact.email)) == email)
        .order_by(Contact.created_at, Contact.id)
        .first()
    )
    created = contact is None
    if created:
        contact = Contact(
            workspace_id=row.workspace_id,
            name=data['name'].strip(),
            email=email,
            phone=data['phone'].strip() or None,
            source=row.source,
        )
        db.session.add(contact)
        db.session.flush()
    if mapped:
        contact.custom_fields = {**(contact.custom_fields or {}), **mapped}
    opportunity = Opportunity(
        workspace_id=row.workspace_id,
        contact_id=contact.id,
        stage_id=row.stage_id,
        title=f'{row.name}: {data["name"].strip()}'[:180],
    )
    db.session.add(opportunity)
    db.session.flush()
    submission = FormSubmission(
        workspace_id=row.workspace_id,
        form_id=row.id,
        submission_key=data['submission_key'],
        contact_id=contact.id,
        opportunity_id=opportunity.id,
        consent_text=consent_text(row),
        answers={'name': data['name'].strip(), 'email': email, 'phone': data['phone'].strip(), **answers},
        attribution=data['attribution'],
    )
    db.session.add(submission)
    try:
        db.session.flush()  # Claim this submission key before dispatching actions.
        record_conversion(row.workspace_id, data['attribution'])
        if created:
            emit(row.workspace_id, 'contact.created', contact.id, contact, opportunity.id)
        emit(row.workspace_id, 'opportunity.created', opportunity.id, contact, opportunity.id, source=row.source)
        emit(row.workspace_id, 'form.submitted', submission.id, contact, opportunity.id, source=row.source)
        db.session.add(
            AuditLog(
                workspace_id=row.workspace_id,
                action='public_form_submit',
                resource='form_submissions',
                resource_id=submission.id,
                details={'form_id': row.id},
            )
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if not FormSubmission.query.filter_by(form_id=row.id, submission_key=data['submission_key']).first():
            raise
