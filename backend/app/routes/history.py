from flask import Blueprint, g, request

from ..common import APIError, audit, query, require
from ..extensions import db, limiter
from ..models import HistorySync, Workspace, uid
from ..services.history import source

bp = Blueprint('history', __name__)


def public(row):
    if not row:
        return None
    # Instagram workspaces may hold several accounts; the screen shows which one is being imported.
    return {**row.public(), **({'connection_id': row.connection_id} if row.channel == 'instagram' else {})}


@bp.get('/history-sync/<channel>')
@require('owner', 'admin')
def status(channel):
    if channel not in ('whatsapp', 'instagram'):
        raise APIError('Canal inválido.', 404)
    row = query(HistorySync).filter_by(channel=channel).first()
    return {'sync': public(row)}


@bp.post('/history-sync/<channel>')
@require('owner', 'admin')
@limiter.limit('20 per minute')
def change(channel):
    if channel not in ('whatsapp', 'instagram'):
        raise APIError('Canal inválido.', 404)
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get('action') not in ('start', 'resume', 'cancel'):
        raise APIError('Ação inválida.', 422)
    action = data['action']
    # Serialize creation and control changes; the worker holds the sync lock per batch.
    Workspace.query.filter_by(id=g.workspace_id).with_for_update().one()
    row = query(HistorySync).filter_by(channel=channel).with_for_update().first()
    if action == 'cancel':
        if row and row.status in ('queued', 'running'):
            row.status = 'cancelled'
    else:
        requested = data.get('connection_id') if channel == 'instagram' else None
        if requested is not None and not isinstance(requested, str):
            raise APIError('Conta inválida.', 422)
        if action == 'resume' and row and not requested:
            requested = row.connection_id if channel == 'instagram' else None
        connection, identity = source(channel, g.workspace_id, requested)
        if row and row.status in ('queued', 'running'):
            return {'sync': public(row)}
        if action == 'resume':
            if not row or row.status not in ('failed', 'cancelled'):
                raise APIError('Não há sincronização para retomar.', 409)
            if row.connection_id != connection.id or row.identity != identity:
                raise APIError('A conexão mudou. Inicie uma nova sincronização.', 409)
            row.status, row.error = 'queued', None
        else:
            if not row:
                row = HistorySync(workspace_id=g.workspace_id, channel=channel)
                db.session.add(row)
            row.connection_id, row.identity = connection.id, identity
            row.status, row.error = 'queued', None
            row.phase = 'mapping' if channel == 'whatsapp' else 'conversations'
            row.cursor = {'run_id': uid(), **({'page': 1, 'mappings': {}} if channel == 'whatsapp' else {})}
            row.scanned = row.imported = row.duplicates = row.skipped = row.unresolved = row.total = 0
    if row:
        db.session.flush()
        audit('history.' + action, row, {'channel': channel})
    db.session.commit()
    return {'sync': public(row)}
