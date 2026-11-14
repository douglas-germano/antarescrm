from flask import g, request
from marshmallow import fields as f
from sqlalchemy import func

from ...common import APIError, add, commit, get, page, payload, query, require, update
from ...extensions import db
from ...models import (
    AutomationJob,
    AutomationRule,
    AutomationRuleVersion,
    AutomationRun,
    Contact,
    Opportunity,
)
from ...schemas.base import StrictSchema, ref
from ...schemas.growth import RuleSchema
from ...services.conditions import explain, matches
from ...services.rule_versions import ensure_baseline, history, record, snapshot
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
    row = add(AutomationRule, data)
    record(row, g.user.id, 'Criada')
    return commit(row, 201)


@bp.patch('/automations/<uuid:rule_id>')
@require('owner', 'admin')
def rule_update(rule_id):
    row = get(AutomationRule, rule_id)
    data = payload(RuleSchema, partial=True)
    validate_rule(data, row)
    ensure_baseline(row)
    update(row, data)
    record(row, g.user.id)
    return commit(row)


@bp.delete('/automations/<uuid:rule_id>')
@require('owner', 'admin')
def rule_delete(rule_id):
    row = get(AutomationRule, rule_id)
    if query(AutomationRun).filter_by(rule_id=row.id).first():
        raise APIError('Esta automação já foi executada e mantém histórico. Pause-a em vez de excluir.', 409)
    query(AutomationRuleVersion).filter_by(rule_id=row.id).delete()
    db.session.delete(row)
    db.session.commit()
    return '', 204


@bp.get('/automations/<uuid:rule_id>/versions')
@require('owner', 'admin')
def rule_versions(rule_id):
    return {'items': history(get(AutomationRule, rule_id))}


@bp.post('/automations/<uuid:rule_id>/versions/<int:number>/restore')
@require('owner', 'admin')
def rule_restore(rule_id, number):
    row = get(AutomationRule, rule_id, lock=True)
    version = query(AutomationRuleVersion).filter_by(rule_id=row.id, number=number).first()
    if not version:
        raise APIError('Versão não encontrada.', 404)
    if version.snapshot == snapshot(row):
        raise APIError('Esta já é a versão em uso.', 409)
    # Saved versions are revalidated: a template, stage or user may no longer exist in the account.
    data = dict(version.snapshot)
    validate_rule(data, row)
    ensure_baseline(row)
    update(row, data)
    record(row, g.user.id, f'Restaurada da versão {number}')
    return commit(row)


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


class PreviewSchema(StrictSchema):
    rule = f.Nested(RuleSchema, required=True)
    opportunity_id = ref(required=True)
    reply_received = f.Boolean(load_default=False)


@bp.post('/automations/preview')
@require('owner', 'admin')
def rule_preview():
    data = payload(PreviewSchema)
    rule = data['rule']
    validate_rule(rule)
    deal = get(Opportunity, data['opportunity_id'])
    if not deal.contact_id:
        raise APIError('Escolha um negócio vinculado a um contato.', 422)
    contact = get(Contact, deal.contact_id)
    # Each filter of the trigger with what it saw, so the test says why the contact entered or not.
    gates = [
        {
            'label': 'Contato ativo',
            'passed': not contact.archived,
            'actual': 'arquivado' if contact.archived else 'ativo',
        }
    ]
    if rule.get('source'):
        gates.append(
            {
                'label': 'Origem é ' + rule['source'],
                'passed': rule['source'].casefold() == (contact.source or '').casefold(),
                'actual': contact.source,
            }
        )
    if rule.get('required_tag'):
        gates.append(
            {
                'label': 'Tem a tag ' + rule['required_tag'],
                'passed': rule['required_tag'] in (contact.tags or []),
                'actual': contact.tags or [],
            }
        )
    if rule['event'] == 'opportunity.stage_idle':
        gates.append({'label': 'Negócio em aberto', 'passed': deal.status == 'open', 'actual': deal.status})
    conditions = rule.get('conditions') or {}
    checks = explain(conditions, contact, deal)
    if checks:
        gates.append(
            {
                'label': 'Condições do gatilho ('
                + ('qualquer uma' if conditions.get('mode') == 'any' else 'todas')
                + ')',
                'passed': matches(conditions, contact, deal),
                'checks': checks,
            }
        )
    eligible = all(gate['passed'] for gate in gates)
    steps = []
    actions = rule.get('actions') or []
    while eligible and actions:
        for action in actions:
            kind = action['kind']
            if kind == 'branch':
                waiting = bool(action.get('wait_reply_minutes'))
                matched = data['reply_received'] if waiting else matches(action.get('conditions', {}), contact, deal)
                steps.append(
                    {
                        'kind': kind,
                        'outcome': ('Resposta recebida' if matched else 'Prazo venceu')
                        if waiting
                        else ('Sim' if matched else 'Não'),
                        'checks': [] if waiting else explain(action.get('conditions', {}), contact, deal),
                        'delay_minutes': action.get('delay_minutes', 0),
                    }
                )
                actions = action['yes' if matched else 'no']
                break
            applies = matches(action.get('conditions', {}), contact, deal)
            steps.append(
                {
                    'kind': kind,
                    'title': action.get('title'),
                    'outcome': 'Executaria' if applies else 'Condição não atendida',
                    'checks': explain(action.get('conditions', {}), contact, deal),
                    'delay_minutes': action.get('delay_minutes', 0),
                    # The test never sends; this marks the steps that would reach the contact for real.
                    'sends_message': applies and kind in SENDS_MESSAGE,
                }
            )
        else:
            break
    return {'eligible': eligible, 'gates': gates, 'steps': steps}


SENDS_MESSAGE = ('send_message', 'reply_comment', 'private_reply', 'instagram_message')
