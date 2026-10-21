"""Opportunity lifecycle: creation, stage moves, closing, and list enrichment."""

from flask import g
from sqlalchemy import func

from ..common import APIError, active, add, get, query, update, user_ref
from ..models import Activity, Company, Contact, Opportunity, PipelineStage, StageHistory, now
from .automations import emit
from .projects import create_from_deal


def validate(data):
    if data.get('contact_id'):
        active(Contact, data['contact_id'], 'O contato')
    if data.get('company_id'):
        active(Company, data['company_id'], 'A empresa')
    if data.get('stage_id'):
        get(PipelineStage, data['stage_id'])
    user_ref(data.get('owner_id'))


def enrich(items):
    """Adds `stage_changed_at` (last stage move) and `last_contact_at` (last completed activity) to listed deals."""
    ids = [row['id'] for row in items]
    if not ids:
        return
    moved = dict(
        query(StageHistory)
        .filter(StageHistory.opportunity_id.in_(ids))
        .with_entities(StageHistory.opportunity_id, func.max(StageHistory.created_at))
        .group_by(StageHistory.opportunity_id)
        .all()
    )
    touched = dict(
        query(Activity)
        .filter(Activity.opportunity_id.in_(ids), Activity.status == 'completed')
        .with_entities(Activity.opportunity_id, func.max(Activity.scheduled_at))
        .group_by(Activity.opportunity_id)
        .all()
    )
    for row in items:
        when = moved.get(row['id'])
        row['stage_changed_at'] = when.isoformat() if when else row.get('created_at')
        last = touched.get(row['id'])
        row['last_contact_at'] = last.isoformat() if last else None


def create(data, user_id):
    validate(data)
    if not data.get('company_id') and data.get('contact_id'):
        data['company_id'] = get(Contact, data['contact_id']).company_id
    row = add(Opportunity, data)
    add(StageHistory, {'opportunity_id': row.id, 'to_stage_id': row.stage_id, 'user_id': user_id})
    if row.contact_id:
        emit(g.workspace_id, 'opportunity.created', row.id, get(Contact, row.contact_id), row.id)
    return row


def modify(row, data, user_id):
    if row.status != 'open':
        raise APIError('Negócios encerrados não podem ser alterados.', 409)
    validate(data)
    history = None
    if data.get('stage_id', row.stage_id) != row.stage_id:
        history = add(
            StageHistory,
            {
                'opportunity_id': row.id,
                'from_stage_id': row.stage_id,
                'to_stage_id': data['stage_id'],
                'user_id': user_id,
            },
        )
    update(row, data)
    if history and row.contact_id:
        emit(g.workspace_id, 'opportunity.stage_changed', history.id, get(Contact, row.contact_id), row.id)
    return row


def close(row, data, user_id):
    if row.status != 'open':
        raise APIError('Negócio já encerrado.', 409)
    if data['status'] == 'lost' and not data.get('loss_reason'):
        raise APIError('Informe o motivo da perda.')
    if data['status'] == 'won' and row.amount <= 0:
        raise APIError('Informe um valor positivo para fechar a venda.')
    update(row, {'status': data['status'], 'closed_at': now(), 'loss_reason': data.get('loss_reason')})
    if data['status'] == 'won':
        create_from_deal(row, user_id)
    if row.contact_id:
        emit(g.workspace_id, 'opportunity.' + data['status'], row.id, get(Contact, row.contact_id), row.id)
    return row
