from flask import Blueprint, g, request

from ..common import APIError, audit, commit, get, page, payload, query, require
from ..extensions import db, limiter
from ..models import CustomDomain, Funnel
from ..schemas.domains import DomainSchema, DomainUpdateSchema
from ..services import domains as service

bp = Blueprint('domains', __name__)


@bp.get('/domains')
@require()
def domains():
    return page(query(CustomDomain).order_by(CustomDomain.created_at), serializer=service.serialize)


@bp.get('/domains/setup')
@require('owner', 'admin')
def domain_setup():
    return service.setup_info()


@bp.post('/domains')
@require('owner', 'admin')
def domain_create():
    data = payload(DomainSchema)
    if data.get('funnel_id'):
        get(Funnel, data['funnel_id'])
    row = service.create(data['hostname'], data.get('funnel_id'), g.workspace_id)
    audit('create', row)
    return commit(row, 201, service.serialize)


@bp.patch('/domains/<uuid:domain_id>')
@require('owner', 'admin')
def domain_update(domain_id):
    row = get(CustomDomain, domain_id)
    service.set_funnel(row, payload(DomainUpdateSchema)['funnel_id'])
    audit('update', row, {'fields': ['funnel_id']})
    return commit(row, serializer=service.serialize)


@bp.post('/domains/<uuid:domain_id>/verify')
@require('owner', 'admin')
def domain_verify(domain_id):
    row = service.verify(get(CustomDomain, domain_id))
    return commit(row, serializer=service.serialize)


@bp.delete('/domains/<uuid:domain_id>')
@require('owner', 'admin')
def domain_delete(domain_id):
    row = get(CustomDomain, domain_id)
    audit('delete', row, {'hostname': row.hostname})
    service.release(row)
    db.session.delete(row)
    db.session.commit()
    return '', 204


@bp.get('/public/domains/resolve')
@limiter.limit('600 per minute')
def domain_resolve():
    host = request.args.get('host', '')
    if len(host) > 253:
        raise APIError('Domínio não configurado.', 404)
    return service.resolve(host)
