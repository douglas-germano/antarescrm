from flask import g, request

from ...common import APIError, get, page, query, require
from ...extensions import db
from ...models import (
    AutomationJob,
    AutomationRun,
    Contact,
    now,
)
from ...services.automations import process
from . import bp


@bp.get('/automations/jobs')
@require()
def jobs():
    q = query(AutomationJob)
    if request.args.get('status'):
        q = q.filter(AutomationJob.status == request.args['status'])
    result = page(q.order_by(AutomationJob.scheduled_at.desc()))
    run_ids = [row['run_id'] for row in result['items']]
    if run_ids:
        runs_by_id = {r.id: r for r in query(AutomationRun).filter(AutomationRun.id.in_(run_ids)).all()}
        contacts = {
            c.id: c.name
            for c in query(Contact).filter(Contact.id.in_([r.contact_id for r in runs_by_id.values()])).all()
        }
        for row in result['items']:
            run = runs_by_id.get(row['run_id'])
            row['rule_id'] = run.rule_id if run else None
            row['contact_name'] = contacts.get(run.contact_id) if run else None
    return result


@bp.post('/automations/jobs/<uuid:job_id>/cancel')
@require('owner', 'admin')
def job_cancel(job_id):
    job = get(AutomationJob, job_id, lock=True)
    if job.status != 'pending':
        raise APIError('Somente etapas pendentes podem ser canceladas.', 409)
    job.status, job.detail = 'cancelled', 'Cancelada manualmente.'
    db.session.commit()
    return job.to_dict()


@bp.post('/automations/jobs/<uuid:job_id>/retry')
@require('owner', 'admin')
def job_retry(job_id):

    job = get(AutomationJob, job_id, lock=True)
    if job.status not in ('failed', 'skipped'):
        raise APIError('Somente etapas que falharam ou foram ignoradas podem ser reprocessadas.', 409)
    job.status, job.detail, job.scheduled_at = 'pending', 'Reprocessamento solicitado.', now()
    run = db.session.get(AutomationRun, job.run_id)
    run.status, run.detail = 'queued', 'Etapas agendadas.'
    db.session.commit()
    return job.to_dict()


@bp.post('/automations/process')
@require('owner', 'admin')
def process_jobs():

    return {'items': process(g.workspace_id, limit=50)}
