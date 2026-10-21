from flask import request

from ...common import APIError, add, commit, get, page, payload, query, require, update
from ...extensions import limiter
from ...models import (
    FormSubmission,
    LeadForm,
    PipelineStage,
)
from ...schemas.growth import FormSchema, SubmissionSchema
from ...services.form_design import validate_settings
from ...services.form_fields import validate_definitions
from ...services.form_submission import after_submit, public_payload, published_form
from ...services.form_submission import submit as submit_form
from . import bp


@bp.get('/forms')
@require()
def forms():
    return page(query(LeadForm).order_by(LeadForm.created_at.desc()))


@bp.post('/forms')
@require('owner', 'admin')
def form_create():
    data = payload(FormSchema)
    validate_definitions(data.get('fields', []))
    validate_settings(data.get('settings'))
    get(PipelineStage, data['stage_id'])
    return commit(add(LeadForm, data), 201)


@bp.get('/forms/<uuid:form_id>')
@require()
def form_detail(form_id):
    return get(LeadForm, form_id).to_dict()


@bp.patch('/forms/<uuid:form_id>')
@require('owner', 'admin')
def form_update(form_id):
    row = get(LeadForm, form_id)
    data = payload(FormSchema, partial=True)
    if 'fields' in data:
        validate_definitions(data['fields'])
    if 'settings' in data:
        validate_settings(data['settings'])
    if data.get('stage_id'):
        get(PipelineStage, data['stage_id'])
    update(row, data)
    return commit(row)


@bp.get('/forms/<uuid:form_id>/submissions')
@require()
def submissions(form_id):
    row = get(LeadForm, form_id)
    return page(query(FormSubmission).filter_by(form_id=row.id).order_by(FormSubmission.created_at.desc()))


@bp.get('/public/forms/<uuid:form_id>')
@limiter.limit('60 per minute')
def public_form(form_id):
    return public_payload(published_form(form_id))


@bp.post('/public/forms/<uuid:form_id>/submit')
@limiter.limit('10 per minute; 100 per hour')
def public_submit(form_id):
    row = published_form(form_id)
    if request.content_length and request.content_length > 8192:
        raise APIError('Solicitação muito grande.', 413)
    data = payload(SubmissionSchema)
    submit_form(row, data)
    # Never return contact details, identifiers or whether an email already existed.
    after = after_submit(row)
    response = {'message': row.success_message}
    if after['type'] == 'redirect':
        response['redirect_url'] = after['url']
    return response, 200
