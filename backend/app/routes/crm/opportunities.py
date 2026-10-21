from flask import g, request

from ...common import commit, get, page, payload, query, require
from ...models import Opportunity, Pipeline, PipelineStage, StageHistory
from ...schemas import CloseSchema, OpportunitySchema
from ...services import opportunities as opportunity_service
from . import bp
from ._search import search


@bp.get('/opportunities')
@require()
def opportunities():
    q = query(Opportunity)
    identifier = request.args.get('pipeline_id')
    if identifier:
        if identifier != 'default':
            get(Pipeline, identifier)
        q = q.join(PipelineStage, PipelineStage.id == Opportunity.stage_id).filter(
            PipelineStage.pipeline_id.is_(None) if identifier == 'default' else PipelineStage.pipeline_id == identifier
        )
    for field in ('status', 'stage_id', 'contact_id', 'company_id', 'owner_id'):
        if request.args.get(field):
            q = q.filter(getattr(Opportunity, field) == request.args[field])
    q = search(q, Opportunity, 'title')
    result = page(q.order_by(Opportunity.updated_at.desc()))
    opportunity_service.enrich(result['items'])
    return result


@bp.post('/opportunities')
@require()
def opportunity_create():
    data = payload(OpportunitySchema)
    return commit(opportunity_service.create(data, g.user.id), 201)


@bp.get('/opportunities/<uuid:opportunity_id>')
@require()
def opportunity_detail(opportunity_id):
    row = get(Opportunity, opportunity_id)
    history = query(StageHistory).filter_by(opportunity_id=row.id).order_by(StageHistory.created_at).all()
    return {
        **row.to_dict(),
        'pipeline_id': get(PipelineStage, row.stage_id).pipeline_id,
        'history': [x.to_dict() for x in history],
    }


@bp.patch('/opportunities/<uuid:opportunity_id>')
@require()
def opportunity_update(opportunity_id):
    row = get(Opportunity, opportunity_id, lock=True)
    data = payload(OpportunitySchema, partial=True)
    return commit(opportunity_service.modify(row, data, g.user.id))


@bp.post('/opportunities/<uuid:opportunity_id>/close')
@require()
def opportunity_close(opportunity_id):
    row = get(Opportunity, opportunity_id, lock=True)
    data = payload(CloseSchema)
    return commit(opportunity_service.close(row, data, g.user.id))
