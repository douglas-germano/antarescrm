from flask import g, request

from ...common import commit, get, page, payload, query, require
from ...models import Opportunity, PipelineStage, StageHistory
from ...schemas import CloseSchema, OpportunitySchema
from ...services import crm_lists as lists
from ...services import opportunities as opportunity_service
from . import bp


@bp.get('/opportunities')
@require()
def opportunities():
    q = lists.opportunity_query(request.args)
    summary = lists.opportunity_summary(q)
    result = page(lists.opportunity_order(q, request.args))
    result['summary'] = summary
    result['sources'] = lists.contact_sources()
    lists.enrich_people(result['items'])
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
    data = row.to_dict()
    lists.enrich_people([data])
    return {
        **data,
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
