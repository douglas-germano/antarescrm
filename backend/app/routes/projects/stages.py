from flask import g
from sqlalchemy import func

from ...common import APIError, add, audit, commit, get, payload, query, require, update
from ...extensions import db
from ...models import (
    Project,
    ProjectStage,
)
from ...schemas import ProjectStageSchema
from ...services import projects as service

# ---------- schemas ----------
from . import bp
from .serializers import stage_dict


@bp.get('/project-stages')
@require()
def stages():
    service.ensure_stages(g.workspace_id)
    db.session.commit()
    return {'items': [stage_dict(s) for s in query(ProjectStage).order_by(ProjectStage.position).all()]}


@bp.post('/project-stages')
@require('owner', 'admin')
def stage_create():
    data = payload(ProjectStageSchema)
    service.ensure_stages(g.workspace_id)
    if query(ProjectStage).filter(func.lower(ProjectStage.name) == data['name'].lower()).first():
        raise APIError('Já existe uma etapa com este nome.', 409)
    data.setdefault('position', query(ProjectStage).count())
    return commit(add(ProjectStage, data), 201)


@bp.patch('/project-stages/<uuid:stage_id>')
@require('owner', 'admin')
def stage_update(stage_id):
    row = get(ProjectStage, stage_id)
    data = payload(ProjectStageSchema, partial=True)
    if (
        'name' in data
        and query(ProjectStage)
        .filter(func.lower(ProjectStage.name) == data['name'].lower(), ProjectStage.id != row.id)
        .first()
    ):
        raise APIError('Já existe uma etapa com este nome.', 409)
    update(row, data)
    return commit(row)


@bp.delete('/project-stages/<uuid:stage_id>')
@require('owner', 'admin')
def stage_delete(stage_id):
    row = get(ProjectStage, stage_id)
    if query(Project).filter_by(stage_id=row.id).first():
        raise APIError('Mova os projetos desta etapa antes de excluí-la.', 409)
    if query(ProjectStage).count() <= 1:
        raise APIError('Mantenha pelo menos uma etapa.', 409)
    audit('delete', row)
    db.session.delete(row)
    db.session.commit()
    return '', 204
