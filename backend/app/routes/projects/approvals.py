import hashlib

from flask import g, request

from ...common import APIError, add, get, payload, query, require
from ...extensions import db, limiter
from ...models import (
    Project,
    ProjectApproval,
    ProjectFile,
    Workspace,
    now,
)
from ...schemas import ApprovalSchema, DecisionSchema
from ...services import projects as service

# ---------- schemas ----------
from . import bp
from .files import file_response
from .serializers import approval_dict, file_dict


@bp.post('/projects/<uuid:project_id>/approvals')
@require()
def approval_create(project_id):
    project = get(Project, project_id)
    data = payload(ApprovalSchema)
    file = None
    if data.get('file_id'):
        file = query(ProjectFile).filter_by(id=str(data['file_id']), project_id=project.id, archived=False).first()
        if not file:
            raise APIError('Arquivo não encontrado neste projeto.', 404)
    row = add(
        ProjectApproval,
        {
            'project_id': project.id,
            'file_id': file.id if file else None,
            'title': data['title'],
            'message': data.get('message'),
            'channel': data['channel'],
            'requested_by': g.user.id,
        },
    )
    token = service.new_token(row, data['expires_days']) if data['channel'] == 'public' else None
    service.log_event(
        project,
        'approval',
        f'Aprovação solicitada: “{data["title"]}”' + (f' (v{file.version})' if file else '') + '.',
        g.user.id,
    )
    db.session.commit()
    result = approval_dict(row, {file.id: file} if file else {})
    result['token'] = token  # Shown once; only its hash is stored.
    return result, 201


@bp.post('/projects/<uuid:project_id>/approvals/<uuid:approval_id>/regenerate')
@require()
def approval_regenerate(project_id, approval_id):
    row = query(ProjectApproval).filter_by(id=str(approval_id), project_id=str(project_id)).first()
    if not row:
        raise APIError('Solicitação não encontrada.', 404)
    if row.status != 'pending':
        raise APIError('Esta solicitação já foi respondida ou cancelada.', 409)
    token = service.new_token(row, 30)
    row.channel = 'public'
    db.session.commit()
    return {'token': token}


@bp.post('/projects/<uuid:project_id>/approvals/<uuid:approval_id>/cancel')
@require()
def approval_cancel(project_id, approval_id):
    project = get(Project, project_id)
    row = query(ProjectApproval).filter_by(id=str(approval_id), project_id=project.id).first()
    if not row:
        raise APIError('Solicitação não encontrada.', 404)
    if row.status != 'pending':
        raise APIError('Esta solicitação já foi respondida ou cancelada.', 409)
    row.status, row.token_hash = 'cancelled', None
    service.log_event(project, 'approval', f'Solicitação cancelada: “{row.title}”.', g.user.id)
    db.session.commit()
    return {'ok': True}


@bp.post('/projects/<uuid:project_id>/approvals/<uuid:approval_id>/decide')
@require()
def approval_decide(project_id, approval_id):
    project = get(Project, project_id)
    row = query(ProjectApproval).filter_by(id=str(approval_id), project_id=project.id).with_for_update().first()
    if not row:
        raise APIError('Solicitação não encontrada.', 404)
    if row.status != 'pending':
        raise APIError('Esta solicitação já foi respondida ou cancelada.', 409)
    data = payload(DecisionSchema)
    if data['decision'] == 'changes_requested' and not (data.get('comment') or '').strip():
        raise APIError('Descreva os ajustes solicitados.', 422)
    service.record_decision(
        project, row, data['decision'], data['name'], data.get('comment'), None, 'internal', g.user.id
    )
    db.session.commit()
    return {'ok': True}


@bp.get('/public/approvals/<token>')
@limiter.limit('60 per minute')
def public_approval(token):
    row = service.by_token(token)
    project = db.session.get(Project, row.project_id)
    workspace = db.session.get(Workspace, row.workspace_id)
    file = db.session.get(ProjectFile, row.file_id) if row.file_id else None
    expired = bool(row.expires_at and row.expires_at <= now())
    return {
        'title': row.title,
        'message': row.message,
        'project': project.title,
        'company': workspace.name,
        'status': 'expired' if expired and row.status == 'pending' else row.status,
        'file': {
            'name': file.title,
            'version': file.version,
            'mimetype': file.mimetype,
            'inline': file_dict(file)['inline'],
        }
        if file
        else None,
    }


@bp.get('/public/approvals/<token>/file')
@limiter.limit('60 per minute')
def public_approval_file(token):
    row = service.by_token(token)
    if row.expires_at and row.expires_at <= now() and row.status == 'pending':
        raise APIError('Link inválido ou expirado.', 404)
    file = db.session.get(ProjectFile, row.file_id) if row.file_id else None
    if not file:
        raise APIError('Esta solicitação não tem arquivo.', 404)
    return file_response(file, request.args.get('inline') == '1')


@bp.post('/public/approvals/<token>/decide')
@limiter.limit('10 per minute;60 per hour')
def public_decide(token):
    if request.content_length and request.content_length > 8192:
        raise APIError('Solicitação muito grande.', 413)
    row = (
        ProjectApproval.query.filter_by(token_hash=hashlib.sha256(token.encode()).hexdigest()).with_for_update().first()
    )
    if not row or row.status == 'cancelled':
        raise APIError('Link inválido ou expirado.', 404)
    if row.status != 'pending':
        raise APIError('Esta solicitação já foi respondida.', 409)
    if row.expires_at and row.expires_at <= now():
        raise APIError('Este link expirou. Peça um novo link à equipe.', 410)
    data = payload(DecisionSchema)
    if data['decision'] == 'changes_requested' and not (data.get('comment') or '').strip():
        raise APIError('Descreva os ajustes que você deseja.', 422)
    project = db.session.get(Project, row.project_id)
    service.record_decision(
        project,
        row,
        data['decision'],
        data['name'],
        data.get('comment'),
        request.headers.get('X-Client-IP') or request.remote_addr,
        'public',
    )
    db.session.commit()
    return {'message': 'Resposta registrada. Obrigado!', 'status': row.status}
