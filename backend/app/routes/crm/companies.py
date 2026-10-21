from flask import request

from ...common import add, commit, get, page, payload, query, require, update
from ...models import Company, Contact, Opportunity
from ...schemas import CompanySchema
from . import bp
from ._search import search


@bp.get('/companies')
@require()
def companies():
    q = query(Company).filter_by(archived=request.args.get('archived') == 'true')
    return page(search(q, Company, 'name', 'document', 'email', 'phone').order_by(Company.name))


@bp.post('/companies')
@require()
def company_create():
    return commit(add(Company, payload(CompanySchema)), 201)


@bp.get('/companies/<uuid:company_id>')
@require()
def company_detail(company_id):
    row = get(Company, company_id)
    contacts = query(Contact).filter_by(company_id=row.id, archived=False).order_by(Contact.name).all()
    opportunities = query(Opportunity).filter_by(company_id=row.id).order_by(Opportunity.updated_at.desc()).all()
    return {
        **row.to_dict(),
        'contacts': [c.to_dict() for c in contacts],
        'opportunities': [o.to_dict() for o in opportunities],
    }


@bp.patch('/companies/<uuid:company_id>')
@require()
def company_update(company_id):
    row = get(Company, company_id)
    update(row, payload(CompanySchema, partial=True))
    return commit(row)


@bp.delete('/companies/<uuid:company_id>')
@require()
def company_archive(company_id):
    row = get(Company, company_id)
    update(row, {'archived': True})
    return commit(row)
