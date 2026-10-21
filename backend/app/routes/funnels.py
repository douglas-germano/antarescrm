from flask import Blueprint, request

from ..common import APIError, add, audit, commit, get, page, payload, query, require, update
from ..extensions import db, limiter
from ..models import Funnel, FunnelStep
from ..schemas.funnels import FunnelSchema, ReorderSchema, StepSchema, ViewSchema
from ..services import funnels as service
from ..services.funnel_blocks import clean_theme

bp = Blueprint('funnels', __name__)


def _funnel_with_steps(funnel):
    return service.serialize(funnel, service.ordered_steps(funnel.id))


def _step(funnel_id, step_id):
    funnel = get(Funnel, funnel_id)
    step = query(FunnelStep).filter_by(id=str(step_id), funnel_id=funnel.id).first()
    if not step:
        raise APIError('Registro não encontrado.', 404)
    return funnel, step


@bp.get('/funnels')
@require()
def funnels():
    result = page(query(Funnel).order_by(Funnel.created_at.desc()), serializer=service.serialize)
    totals = service.totals_for([item['id'] for item in result['items']])
    for item in result['items']:
        item['totals'] = totals[item['id']]
    return result


@bp.post('/funnels')
@require('owner', 'admin')
def funnel_create():
    data = payload(FunnelSchema)
    template = data.pop('template')
    data['theme'] = clean_theme(data.get('theme', {}))
    row = add(Funnel, data)
    service.build_template(row, template)
    return commit(row, 201, _funnel_with_steps)


@bp.get('/funnels/<uuid:funnel_id>')
@require()
def funnel_detail(funnel_id):
    return _funnel_with_steps(get(Funnel, funnel_id))


@bp.patch('/funnels/<uuid:funnel_id>')
@require('owner', 'admin')
def funnel_update(funnel_id):
    row = get(Funnel, funnel_id)
    data = payload(FunnelSchema, partial=True)
    data.pop('template', None)
    if 'theme' in data:
        data['theme'] = clean_theme(data['theme'])
    status = data.pop('status', None)
    update(row, data)
    if status == 'published':
        service.publish(row)
    elif status:
        row.status = status
    return commit(row, serializer=_funnel_with_steps)


@bp.delete('/funnels/<uuid:funnel_id>')
@require('owner', 'admin')
def funnel_delete(funnel_id):
    row = get(Funnel, funnel_id)
    audit('delete', row)
    service.delete_funnel(row)
    db.session.commit()
    return '', 204


@bp.post('/funnels/<uuid:funnel_id>/duplicate')
@require('owner', 'admin')
def funnel_duplicate(funnel_id):
    row = get(Funnel, funnel_id)
    copy = service.duplicate(row, f'{row.name} (cópia)'[:150])
    audit('create', copy, {'copied_from': row.id})
    return commit(copy, 201, _funnel_with_steps)


@bp.get('/funnels/<uuid:funnel_id>/stats')
@require()
def funnel_stats(funnel_id):
    return service.stats(get(Funnel, funnel_id))


@bp.post('/funnels/<uuid:funnel_id>/steps')
@require('owner', 'admin')
def step_create(funnel_id):
    funnel = get(Funnel, funnel_id)
    data = service.prepare_step_data(funnel.id, payload(StepSchema))
    step = service.add_step(funnel, data['name'], data.get('kind', 'custom'), data.get('blocks'), data.get('settings'))
    if data.get('slug'):
        step.slug = data['slug']
    audit('create', step)
    return commit(step, 201)


@bp.post('/funnels/<uuid:funnel_id>/steps/reorder')
@require('owner', 'admin')
def steps_reorder(funnel_id):
    funnel = get(Funnel, funnel_id)
    service.reorder(funnel, payload(ReorderSchema)['order'])
    db.session.commit()
    return _funnel_with_steps(funnel)


@bp.patch('/funnels/<uuid:funnel_id>/steps/<uuid:step_id>')
@require('owner', 'admin')
def step_update(funnel_id, step_id):
    funnel, step = _step(funnel_id, step_id)
    data = service.prepare_step_data(funnel.id, payload(StepSchema, partial=True), step)
    update(step, data)
    return commit(step)


@bp.delete('/funnels/<uuid:funnel_id>/steps/<uuid:step_id>')
@require('owner', 'admin')
def step_delete(funnel_id, step_id):
    funnel, step = _step(funnel_id, step_id)
    audit('delete', step)
    service.delete_step(funnel, step)
    db.session.commit()
    return '', 204


@bp.get('/public/funnels/<uuid:funnel_id>')
@bp.get('/public/funnels/<uuid:funnel_id>/<slug>')
@limiter.limit('120 per minute')
def public_funnel_page(funnel_id, slug=None):
    return service.public_page(funnel_id, slug)


@bp.post('/public/funnels/<uuid:funnel_id>/steps/<uuid:step_id>/view')
@limiter.limit('120 per minute')
def public_funnel_view(funnel_id, step_id):
    if request.content_length and request.content_length > 1024:
        raise APIError('Solicitação muito grande.', 413)
    service.record_view(funnel_id, step_id, payload(ViewSchema)['visitor_id'])
    return '', 204
