from flask import request
from sqlalchemy import func

from ...common import APIError, add, commit, get, page, payload, query, require, update
from ...extensions import db
from ...models import (
    AutomationJob,
    AutomationRule,
    AutomationRun,
    Contact,
)
from ...schemas.growth import RuleSchema
from ...services.rules import validate_rule
from . import bp


@bp.get('/automations')
@require()
def rules():
    result = page(query(AutomationRule).order_by(AutomationRule.created_at.desc()))
    ids = [row['id'] for row in result['items']]
    stats = {}
    if ids:
        for rule_id, status, count, last in (
            query(AutomationRun)
            .filter(AutomationRun.rule_id.in_(ids))
            .with_entities(
                AutomationRun.rule_id,
                AutomationRun.status,
                func.count(AutomationRun.id),
                func.max(AutomationRun.created_at),
            )
            .group_by(AutomationRun.rule_id, AutomationRun.status)
            .all()
        ):
            item = stats.setdefault(rule_id, {'runs': 0, 'failed': 0, 'last_run_at': None})
            item['runs'] += count
            item['failed'] += count if status == 'failed' else 0
            if last and (not item['last_run_at'] or last.isoformat() > item['last_run_at']):
                item['last_run_at'] = last.isoformat()
    for row in result['items']:
        row['stats'] = stats.get(row['id'], {'runs': 0, 'failed': 0, 'last_run_at': None})
    return result


@bp.post('/automations')
@require('owner', 'admin')
def rule_create():
    data = payload(RuleSchema)
    validate_rule(data)
    return commit(add(AutomationRule, data), 201)


@bp.patch('/automations/<uuid:rule_id>')
@require('owner', 'admin')
def rule_update(rule_id):
    row = get(AutomationRule, rule_id)
    data = payload(RuleSchema, partial=True)
    validate_rule(data)
    update(row, data)
    return commit(row)


@bp.delete('/automations/<uuid:rule_id>')
@require('owner', 'admin')
def rule_delete(rule_id):
    row = get(AutomationRule, rule_id)
    if query(AutomationRun).filter_by(rule_id=row.id).first():
        raise APIError('Esta automação já foi executada e mantém histórico. Pause-a em vez de excluir.', 409)
    db.session.delete(row)
    db.session.commit()
    return '', 204


@bp.get('/automations/runs')
@require()
def runs():
    q = query(AutomationRun)
    for field in ('status', 'rule_id'):
        if request.args.get(field):
            q = q.filter(getattr(AutomationRun, field) == request.args[field])
    result = page(q.order_by(AutomationRun.created_at.desc()))
    names = (
        {c.id: c.name for c in query(Contact).filter(Contact.id.in_([r['contact_id'] for r in result['items']])).all()}
        if result['items']
        else {}
    )
    for row in result['items']:
        row['contact_name'] = names.get(row['contact_id'])
    return result


@bp.post('/automations/runs/<uuid:run_id>/cancel')
@require('owner', 'admin')
def run_cancel(run_id):
    run = get(AutomationRun, run_id, lock=True)
    pending = query(AutomationJob).filter_by(run_id=run.id, status='pending').all()
    if not pending:
        raise APIError('Esta execução não tem etapas pendentes.', 409)
    for job in pending:
        job.status, job.detail = 'cancelled', 'Cancelada manualmente.'
    run.status, run.detail = 'cancelled', 'Cancelada manualmente.'
    db.session.commit()
    return run.to_dict()


# Keep each template lookup within the selected account, including nested workflow actions.
