from flask import Blueprint, g, request

from ..common import add, audit, commit, get, page, payload, require, update, user_ref
from ..extensions import db
from ..models import Company, Contact, Opportunity, Task, now
from ..schemas import TaskSchema
from ..services import crm_lists as lists

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
    result = page(lists.task_query(request.args))
    lists.enrich_people(result['items'])
    return result


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
