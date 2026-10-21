from flask import g, request

from ...common import active, add, commit, get, page, payload, query, require, update, user_ref
from ...models import Activity, Company, Contact, Opportunity, Task, WhatsAppConversation
from ...schemas import ContactSchema
from ...services.automations import emit
from . import bp
from ._search import search


@bp.get('/contacts')
@require()
def contacts():
    q = query(Contact).filter_by(archived=request.args.get('archived') == 'true')
    for field in ('company_id', 'owner_id'):
        if request.args.get(field):
            q = q.filter(getattr(Contact, field) == request.args[field])
    return page(search(q, Contact, 'name', 'phone', 'email').order_by(Contact.name))


def validate_contact(data):
    if data.get('company_id'):
        active(Company, data['company_id'], 'A empresa')
    user_ref(data.get('owner_id'))


@bp.post('/contacts')
@require()
def contact_create():
    data = payload(ContactSchema)
    validate_contact(data)
    row = add(Contact, data)

    emit(g.workspace_id, 'contact.created', row.id, row)
    return commit(row, 201)


@bp.get('/contacts/<uuid:contact_id>')
@require()
def contact_detail(contact_id):
    return get(Contact, contact_id).to_dict()


@bp.patch('/contacts/<uuid:contact_id>')
@require()
def contact_update(contact_id):
    row = get(Contact, contact_id)
    data = payload(ContactSchema, partial=True)
    validate_contact(data)
    update(row, data)
    return commit(row)


@bp.delete('/contacts/<uuid:contact_id>')
@require()
def contact_archive(contact_id):
    row = get(Contact, contact_id)
    update(row, {'archived': True})
    return commit(row)


@bp.get('/contacts/<uuid:contact_id>/timeline')
@require()
def contact_timeline(contact_id):
    """Everything that happened with a contact: activities, deals, tasks and the WhatsApp thread."""
    row = get(Contact, contact_id)
    conversation = query(WhatsAppConversation).filter_by(contact_id=row.id).first()
    return {
        'activities': [
            x.to_dict()
            for x in query(Activity).filter_by(contact_id=row.id).order_by(Activity.scheduled_at.desc()).limit(100)
        ],
        'opportunities': [
            x.to_dict() for x in query(Opportunity).filter_by(contact_id=row.id).order_by(Opportunity.updated_at.desc())
        ],
        'tasks': [x.to_dict() for x in query(Task).filter_by(contact_id=row.id).order_by(Task.due_date)],
        'whatsapp_conversation_id': conversation.id if conversation else None,
    }
