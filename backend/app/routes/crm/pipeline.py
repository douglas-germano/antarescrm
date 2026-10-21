from flask import g, request

from ...common import APIError, add, audit, commit, get, payload, query, require, update
from ...extensions import db
from ...models import LeadForm, Opportunity, Pipeline, PipelineStage, StageHistory
from ...schemas import StageSchema, StrictSchema, text
from ...services.booking import lock
from . import bp


@bp.get('/pipeline/stages')
@require()
def stages():
    q = query(PipelineStage)
    identifier = request.args.get('pipeline_id')
    if identifier:
        if identifier != 'default':
            get(Pipeline, identifier)
        q = q.filter_by(pipeline_id=None if identifier == 'default' else identifier)
    names = {row.id: row.name for row in query(Pipeline).all()}
    return {
        'items': [
            {**x.to_dict(), 'pipeline_name': names.get(x.pipeline_id, 'Principal')}
            for x in q.order_by(PipelineStage.position).all()
        ]
    }


@bp.post('/pipeline/stages')
@require('owner', 'admin')
def stage_create():
    data = payload(StageSchema)
    if data.get('pipeline_id'):
        get(Pipeline, data['pipeline_id'])
    validate_stage_name(data)
    return commit(add(PipelineStage, data), 201)


@bp.patch('/pipeline/stages/<uuid:stage_id>')
@require('owner', 'admin')
def stage_update(stage_id):
    row = get(PipelineStage, stage_id)
    data = payload(StageSchema, partial=True)
    if 'pipeline_id' in data and data['pipeline_id'] != row.pipeline_id:
        raise APIError('Não é possível mover uma etapa para outro funil.', 422)
    validate_stage_name(data, row)
    update(row, data)
    return commit(row)


@bp.delete('/pipeline/stages/<uuid:stage_id>')
@require('owner', 'admin')
def stage_delete(stage_id):
    row = get(PipelineStage, stage_id)
    if (
        query(Opportunity).filter_by(stage_id=row.id).first()
        or query(StageHistory)
        .filter(db.or_(StageHistory.from_stage_id == row.id, StageHistory.to_stage_id == row.id))
        .first()
    ):
        raise APIError('Etapa com negócios ou histórico não pode ser excluída.', 409)

    if query(LeadForm).filter_by(stage_id=row.id).first():
        raise APIError('Etapa vinculada a um formulário não pode ser excluída.', 409)
    audit('delete', row)
    db.session.delete(row)
    db.session.commit()
    return '', 204


def validate_stage_name(data, row=None):
    name = data.get('name', row.name if row else '').strip()
    pipeline_id = row.pipeline_id if row else data.get('pipeline_id')

    lock('stage:' + g.workspace_id + ':' + str(pipeline_id) + ':' + name)
    duplicate = query(PipelineStage).filter_by(pipeline_id=pipeline_id, name=name)
    if row:
        duplicate = duplicate.filter(PipelineStage.id != row.id)
    if duplicate.first():
        raise APIError('Já existe uma etapa com este nome no funil.', 409)
    data['name'] = name


@bp.get('/pipelines')
@require()
def pipelines():
    return {
        'items': [{'id': 'default', 'name': 'Principal'}]
        + [row.to_dict() for row in query(Pipeline).order_by(Pipeline.name)]
    }


@bp.post('/pipelines')
@require('owner', 'admin')
def create_pipeline():

    class Schema(StrictSchema):
        name = text(150, required=True)

    row = add(Pipeline, payload(Schema))
    for index, name in enumerate(('Novo lead', 'Qualificação', 'Proposta', 'Negociação')):
        add(PipelineStage, {'pipeline_id': row.id, 'name': name, 'position': index})
    return commit(row, 201)
