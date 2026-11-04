"""Authenticated, tenant-isolated API for the prospecting copilot."""

from flask import Blueprint, request

from ..common import APIError, audit, current_account, page, payload, require
from ..extensions import db
from ..models import FishingPost
from ..schemas.fishing import DecisionSchema, OpenSchema, PostSchema, SettingsSchema
from ..services import fishing

bp = Blueprint('fishing', __name__)


@bp.get('/fishing/settings')
@require()
def get_settings():
    return fishing.settings_copy(current_account())


@bp.patch('/fishing/settings')
@require('owner', 'admin')
def save_settings():
    account = current_account()
    row = fishing.save_settings(account, payload(SettingsSchema))
    audit('configure', row, {'enabled': row.enabled})
    db.session.commit()
    return fishing.settings_copy(account)


@bp.get('/fishing/posts')
@require()
def posts():
    account = current_account()
    fishing.expire(account.workspace_id)
    db.session.commit()
    status = request.args.get('status', 'na_fila')
    if status not in (
        'todos',
        'novo',
        'processando',
        'na_fila',
        'publicado',
        'pulado',
        'descartado',
        'expirado',
        'erro',
    ):
        raise APIError('Filtro de status inválido.', 422)
    rows = account.query(FishingPost)
    if status != 'todos':
        rows = rows.filter_by(status=status)
    result = page(rows.order_by(FishingPost.score.desc().nullslast(), FishingPost.created_at.desc()))
    fishing.add_latest_drafts(account, result['items'])
    return result


@bp.post('/fishing/posts')
@require()
def add_post():
    account = current_account()
    row = fishing.create_post(account, payload(PostSchema))
    audit('create', row)
    db.session.commit()
    return fishing.serialize(account, row), 201


@bp.get('/fishing/posts/<uuid:identifier>/image')
@require()
def image(identifier):
    return {'image_data': current_account().get(FishingPost, identifier).image_data}


@bp.post('/fishing/posts/<uuid:identifier>/regenerate')
@require()
def regenerate(identifier):
    account = current_account()
    row = account.get(FishingPost, identifier)
    fishing.regenerate(account, row)
    audit('regenerate', row)
    db.session.commit()
    return fishing.serialize(account, row)


@bp.post('/fishing/posts/<uuid:identifier>/open')
@require()
def open_post(identifier):
    account = current_account()
    row = account.get(FishingPost, identifier)
    result = fishing.open_post(account, row, payload(OpenSchema))
    audit('open', row)
    db.session.commit()
    return result


@bp.post('/fishing/posts/<uuid:identifier>/decide')
@require()
def decide(identifier):
    account = current_account()
    row = account.get(FishingPost, identifier)
    fishing.decide(account, row, payload(DecisionSchema)['action'])
    audit('decide', row, {'status': row.status})
    db.session.commit()
    return fishing.serialize(account, row)


@bp.get('/fishing/metrics')
@require()
def metrics():
    return fishing.metrics(current_account())
