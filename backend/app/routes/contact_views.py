from flask import Blueprint, g
from marshmallow import fields as f
from marshmallow import validate

from ..common import APIError, add, audit, commit, page, payload, query, require
from ..extensions import db
from ..models import SavedContactView
from ..schemas import StrictSchema, text
from ..services.booking import lock

bp = Blueprint('contact_views', __name__)


class Filters(StrictSchema):
    search = f.String(validate=validate.Length(max=180), load_default='')
    archived = f.Boolean(load_default=False)
    owner = f.String(validate=validate.Length(max=36), load_default='')
    company = f.String(validate=validate.Length(max=36), load_default='')
    source = f.String(validate=validate.Length(max=100), load_default='')


class ViewSchema(StrictSchema):
    name = text(50, required=True)
    filters = f.Nested(Filters, required=True)


@bp.get('/contact-views')
@require()
def views():
    return page(query(SavedContactView).filter_by(user_id=g.user.id).order_by(SavedContactView.name))


@bp.post('/contact-views')
@require()
def save():
    data = payload(ViewSchema)
    lock('contact-views:' + g.workspace_id + ':' + g.user.id)
    rows = query(SavedContactView).filter_by(user_id=g.user.id)
    if rows.count() >= 20:
        raise APIError('Você pode salvar até 20 visões nesta conta.', 422)
    if any(row.name.casefold() == data['name'].casefold() for row in rows):
        raise APIError('Já existe uma visão com este nome.', 409)
    return commit(add(SavedContactView, {**data, 'user_id': g.user.id}), 201)


@bp.delete('/contact-views/<uuid:identifier>')
@require()
def remove(identifier):
    row = query(SavedContactView).filter_by(id=str(identifier), user_id=g.user.id).first()
    if not row:
        raise APIError('Visão não encontrada.', 404)
    audit('delete', row)
    db.session.delete(row)
    db.session.commit()
    return '', 204
