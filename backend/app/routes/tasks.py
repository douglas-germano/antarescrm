from flask import Blueprint, g, request

from ..common import add, audit, commit, get, page, payload, query, require, update, user_ref
from ..extensions import db
from ..models import Company, Contact, Opportunity, Task, now
from ..schemas import TaskSchema

bp = Blueprint('tasks', __name__)


def validate_task(data):
    for key, model in (('contact_id', Contact), ('company_id', Company), ('opportunity_id', Opportunity)):
        if data.get(key):
            get(model, data[key])
    user_ref(data.get('assignee_id'))


def sync_completion(row, data):
    if 'status' in data:
        data['completed_at'] = now() if data['status'] == 'done' else None
    return data


@bp.get('/tasks')
@require()
def tasks():
    q = query(Task)
    for field in ('status', 'assignee_id', 'contact_id', 'company_id', 'opportunity_id', 'priority'):
        if request.args.get(field):
            q = q.filter(getattr(Task, field) == request.args[field])
    if request.args.get('mine') == 'true':
        q = q.filter(Task.assignee_id == g.user.id)
    if request.args.get('search'):
        q = q.filter(Task.title.ilike('%' + request.args['search'] + '%'))
    return page(q.order_by(Task.due_date.asc().nullslast(), Task.created_at.desc()))


@bp.post('/tasks')
@require()
def task_create():
    data = payload(TaskSchema)
    validate_task(data)
    data.setdefault('assignee_id', g.user.id)
    return commit(add(Task, sync_completion(None, data)), 201)


@bp.patch('/tasks/<uuid:task_id>')
@require()
def task_update(task_id):
    row = get(Task, task_id)
    data = payload(TaskSchema, partial=True)
    validate_task(data)
    update(row, sync_completion(row, data))
    return commit(row)


@bp.delete('/tasks/<uuid:task_id>')
@require()
def task_delete(task_id):
    row = get(Task, task_id)
    audit('delete', row)
    db.session.delete(row)
    db.session.commit()
    return '', 204
