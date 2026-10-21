from flask import g, request

from ...common import add, audit, commit, get, page, payload, query, require, update, user_ref
from ...extensions import db
from ...models import Activity, Company, Contact, Opportunity
from ...schemas import ActivitySchema
from . import bp


def validate_activity(data):
    if data.get('opportunity_id'):
        get(Opportunity, data['opportunity_id'])
    if data.get('contact_id'):
        get(Contact, data['contact_id'])
    if data.get('company_id'):
        get(Company, data['company_id'])
    user_ref(data.get('owner_id'))


@bp.get('/activities')
@require()
def activities():
    q = query(Activity)
    for field in ('opportunity_id', 'contact_id', 'company_id', 'owner_id', 'status', 'kind'):
        if request.args.get(field):
            q = q.filter(getattr(Activity, field) == request.args[field])
    return page(q.order_by(Activity.scheduled_at.desc()))


@bp.post('/activities')
@require()
def activity_create():
    data = payload(ActivitySchema)
    validate_activity(data)
    data.setdefault('owner_id', g.user.id)
    return commit(add(Activity, data), 201)


@bp.patch('/activities/<uuid:activity_id>')
@require()
def activity_update(activity_id):
    row = get(Activity, activity_id)
    data = payload(ActivitySchema, partial=True)
    validate_activity(data)
    update(row, data)
    return commit(row)


@bp.delete('/activities/<uuid:activity_id>')
@require()
def activity_delete(activity_id):
    row = get(Activity, activity_id)
    audit('delete', row)
    db.session.delete(row)
    db.session.commit()
    return '', 204
