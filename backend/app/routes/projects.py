import hashlib
import secrets
from datetime import timedelta
from flask import Blueprint, g, request, send_file
from marshmallow import fields as f, validate
from sqlalchemy import func
from ..common import require, payload, query, get, add, update, commit, page, APIError, user_ref, audit
from ..extensions import db, limiter
from ..models import (Company, Contact, Opportunity, Project, ProjectApproval, ProjectEvent, ProjectFile, ProjectStage, User, Workspace, now)
from ..schemas import StrictSchema, text, choice, ref, money
from ..services import projects as service

bp = Blueprint('projects', __name__)


# ---------- schemas ----------
class StageSchema(StrictSchema):
    name = text(80, required=True)
    position = f.Integer(validate=validate.Range(min=0, max=1000))
    color = f.String(validate=validate.Regexp(r'^#[0-9a-fA-F]{6}$'))
    is_final = f.Boolean()


class ProjectSchema(StrictSchema):
    title = text(180, required=True)
    description = text(5000, allow_none=True)
    contact_id = ref(nullable=True)
    company_id = ref(nullable=True)
    opportunity_id = ref(nullable=True)
    owner_id = ref(nullable=True)
    stage_id = ref()
    amount = money(zero=True)
    status = choice('active done cancelled')
    start_date = f.Date(allow_none=True)
    due_date = f.Date(allow_none=True)


class NoteSchema(StrictSchema):
    text = text(500, required=True)


class ApprovalSchema(StrictSchema):
    file_id = ref(nullable=True)
    title = text(180, required=True)
    message = text(2000, allow_none=True)
    channel = choice('public internal', load_default='public')
    expires_days = f.Integer(validate=validate.Range(min=1, max=180), load_default=30)


class DecisionSchema(StrictSchema):
    decision = choice('approved changes_requested', required=True)
    name = text(150, required=True)
    comment = text(2000, allow_none=True)


class FileMetaSchema(StrictSchema):
    title = text(180)
    kind = choice('layout document other')
    note = text(2000, allow_none=True)


# ---------- helpers ----------
def stage_dict(stage):
    return {'id': stage.id, 'name': stage.name, 'color': stage.color, 'is_final': stage.is_final, 'position': stage.position}


def file_dict(file):
    data = file.to_dict()
    data.pop('storage_key', None)
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    data['inline'] = service.FILE_TYPES.get(ext, ('', False))[1]
    return data


def approval_dict(row, files):
    data = row.to_dict()
    data.pop('token_hash', None)
    data['has_link'] = bool(row.token_hash)
    data['file_title'] = files.get(row.file_id).title if row.file_id in files else None
    data['file_version'] = files.get(row.file_id).version if row.file_id in files else None
    data['expired'] = bool(row.status == 'pending' and row.expires_at and row.expires_at <= now())
    return data


def project_row(project, lookups):
    data = project.to_dict()
    contact = lookups['contacts'].get(project.contact_id)
    data.update({
        'contact_name': contact.name if contact else None, 'company_name': lookups['companies'].get(project.company_id).name if project.company_id in lookups['companies'] else None,
        'owner_name': lookups['users'].get(project.owner_id), 'stage': stage_dict(lookups['stages'][project.stage_id]) if project.stage_id in lookups['stages'] else None,
        'files_count': lookups['files'].get(project.id, 0), 'pending_approvals': lookups['approvals'].get(project.id, 0),
    })
    return data


def lookups_for(rows):
    ids = [r.id for r in rows]
    from ..access import account_users
    return {
        'contacts': {c.id: c for c in query(Contact).filter(Contact.id.in_([r.contact_id for r in rows if r.contact_id])).all()} if rows else {},
        'companies': {c.id: c for c in query(Company).filter(Company.id.in_([r.company_id for r in rows if r.company_id])).all()} if rows else {},
        'users': {u.id: u.name for u in account_users(g.workspace_id)},
        'stages': {s.id: s for s in query(ProjectStage).all()},
        'files': dict(query(ProjectFile).filter(ProjectFile.project_id.in_(ids), ProjectFile.archived.is_(False)).with_entities(ProjectFile.project_id, func.count(func.distinct(ProjectFile.group_id))).group_by(ProjectFile.project_id).all()) if ids else {},
        'approvals': dict(query(ProjectApproval).filter(ProjectApproval.project_id.in_(ids), ProjectApproval.status == 'pending').with_entities(ProjectApproval.project_id, func.count(ProjectApproval.id)).group_by(ProjectApproval.project_id).all()) if ids else {},
    }


def validate_links(data):
    for key, model in (('contact_id', Contact), ('company_id', Company), ('opportunity_id', Opportunity)):
        if data.get(key):
            get(model, data[key])
    if data.get('stage_id'):
        get(ProjectStage, data['stage_id'])
    user_ref(data.get('owner_id'))


def apply_stage(project, stage, user_id):
    previous = db.session.get(ProjectStage, project.stage_id)
    if previous and previous.id == stage.id:
        return
    project.stage_id = stage.id
    service.log_event(project, 'stage', f'Etapa alterada de “{previous.name if previous else "—"}” para “{stage.name}”.', user_id)
    if stage.is_final and project.status == 'active':
        project.status, project.completed_at = 'done', now()
        service.log_event(project, 'status', 'Projeto concluído.', user_id)
    elif not stage.is_final and project.status == 'done':
        project.status, project.completed_at = 'active', None
        service.log_event(project, 'status', 'Projeto reaberto.', user_id)


# ---------- stages ----------
@bp.get('/project-stages')
@require()
def stages():
    service.ensure_stages(g.workspace_id)
    db.session.commit()
    return {'items': [stage_dict(s) for s in query(ProjectStage).order_by(ProjectStage.position).all()]}


@bp.post('/project-stages')
@require('owner', 'admin')
def stage_create():
    data = payload(StageSchema)
    service.ensure_stages(g.workspace_id)
    if query(ProjectStage).filter(func.lower(ProjectStage.name) == data['name'].lower()).first():
        raise APIError('Já existe uma etapa com este nome.', 409)
    data.setdefault('position', query(ProjectStage).count())
    return commit(add(ProjectStage, data), 201)


@bp.patch('/project-stages/<uuid:stage_id>')
@require('owner', 'admin')
def stage_update(stage_id):
    row = get(ProjectStage, stage_id)
    data = payload(StageSchema, partial=True)
    if 'name' in data and query(ProjectStage).filter(func.lower(ProjectStage.name) == data['name'].lower(), ProjectStage.id != row.id).first():
        raise APIError('Já existe uma etapa com este nome.', 409)
    update(row, data)
    return commit(row)


@bp.delete('/project-stages/<uuid:stage_id>')
@require('owner', 'admin')
def stage_delete(stage_id):
    row = get(ProjectStage, stage_id)
    if query(Project).filter_by(stage_id=row.id).first():
        raise APIError('Mova os projetos desta etapa antes de excluí-la.', 409)
    if query(ProjectStage).count() <= 1:
        raise APIError('Mantenha pelo menos uma etapa.', 409)
    audit('delete', row)
    db.session.delete(row)
    db.session.commit()
    return '', 204


# ---------- projects ----------
@bp.get('/projects')
@require()
def projects():
    service.ensure_stages(g.workspace_id)
    q = query(Project)
    for field in ('stage_id', 'status', 'owner_id', 'contact_id', 'opportunity_id'):
        if request.args.get(field):
            q = q.filter(getattr(Project, field) == request.args[field])
    term = (request.args.get('search') or '').strip()
    if term:
        like = '%' + term + '%'
        q = q.outerjoin(Contact, Contact.id == Project.contact_id).filter(db.or_(Project.title.ilike(like), Contact.name.ilike(like)))
    result = q.order_by(Project.updated_at.desc())
    paginated = page(result, serializer=lambda row: row.to_dict())
    rows = [db.session.get(Project, item['id']) for item in paginated['items']]
    look = lookups_for(rows)
    paginated['items'] = [project_row(r, look) for r in rows]
    db.session.commit()
    return paginated


@bp.post('/projects')
@require()
def project_create():
    data = payload(ProjectSchema, partial=True)
    validate_links(data)
    service.ensure_stages(g.workspace_id)
    deal = get(Opportunity, data['opportunity_id']) if data.get('opportunity_id') else None
    if deal:
        existing = query(Project).filter_by(opportunity_id=deal.id).first()
        if existing:
            raise APIError('Este negócio já tem um projeto.', 409, details={'project_id': existing.id})
        data.setdefault('title', deal.title)
        data.setdefault('contact_id', deal.contact_id)
        data.setdefault('company_id', deal.company_id)
        data.setdefault('owner_id', deal.owner_id)
        if not data.get('amount') or float(data['amount']) == 0:
            data['amount'] = deal.amount  # an untouched 0,00 in the form should not hide the negotiated value
        data.setdefault('description', deal.description)
    if not data.get('title'):
        raise APIError('Informe o título do projeto.', 422)
    stage = get(ProjectStage, data['stage_id']) if data.get('stage_id') else service.first_stage(g.workspace_id)
    data['stage_id'] = stage.id
    data.setdefault('start_date', now().date())
    data.pop('status', None)
    row = add(Project, data)
    service.log_event(row, 'created', 'Projeto criado' + (f' a partir do negócio “{deal.title}”.' if deal else '.'), g.user.id)
    return commit(row, 201)


@bp.get('/projects/<uuid:project_id>')
@require()
def project_detail(project_id):
    row = get(Project, project_id)
    look = lookups_for([row])
    data = project_row(row, look)
    deal = db.session.get(Opportunity, row.opportunity_id) if row.opportunity_id else None
    data['deal'] = {'id': deal.id, 'title': deal.title, 'amount': format(deal.amount, '.2f'), 'status': deal.status, 'expected_close_date': deal.expected_close_date.isoformat() if deal.expected_close_date else None,
                    'closed_at': deal.closed_at.isoformat() if deal.closed_at else None} if deal and deal.workspace_id == g.workspace_id else None
    contact = look['contacts'].get(row.contact_id)
    data['contact'] = {'id': contact.id, 'name': contact.name, 'phone': contact.phone, 'email': contact.email} if contact else None
    files = query(ProjectFile).filter_by(project_id=row.id, archived=False).order_by(ProjectFile.version).all()
    groups = {}
    for file in files:
        groups.setdefault(file.group_id, []).append(file)
    data['files'] = [{'group_id': gid, 'title': versions[-1].title, 'kind': versions[-1].kind, 'latest': file_dict(versions[-1]),
                      'versions': [file_dict(v) for v in reversed(versions)]} for gid, versions in sorted(groups.items(), key=lambda kv: kv[1][-1].created_at, reverse=True)]
    by_id = {fl.id: fl for fl in query(ProjectFile).filter_by(project_id=row.id).all()}
    data['approvals'] = [approval_dict(a, by_id) for a in query(ProjectApproval).filter_by(project_id=row.id).order_by(ProjectApproval.created_at.desc()).all()]
    events = query(ProjectEvent).filter_by(project_id=row.id).order_by(ProjectEvent.created_at.desc()).limit(200).all()
    names = look['users']
    data['events'] = [{**e.to_dict(), 'user_name': names.get(e.user_id)} for e in events]
    return data


@bp.patch('/projects/<uuid:project_id>')
@require()
def project_update(project_id):
    row = get(Project, project_id, lock=True)
    data = payload(ProjectSchema, partial=True)
    validate_links(data)
    data.pop('opportunity_id', None)
    stage_id = data.pop('stage_id', None)
    if stage_id:
        apply_stage(row, get(ProjectStage, stage_id), g.user.id)
    status = data.pop('status', None)
    if status and status != row.status:
        row.status = status
        row.completed_at = now() if status == 'done' else None
        service.log_event(row, 'status', {'active': 'Projeto reaberto.', 'done': 'Projeto concluído.', 'cancelled': 'Projeto cancelado.'}[status], g.user.id)
    update(row, data)
    return commit(row)


@bp.delete('/projects/<uuid:project_id>')
@require('owner', 'admin')
def project_delete(project_id):
    row = get(Project, project_id, lock=True)
    files = query(ProjectFile).filter_by(project_id=row.id).all()
    keys = [fl.storage_key for fl in files]
    for model in (ProjectApproval, ProjectEvent, ProjectFile):
        query(model).filter_by(project_id=row.id).delete()
    audit('delete', row)
    db.session.delete(row)
    db.session.commit()
    for key in keys:
        service.delete_bytes(key)
    return '', 204


@bp.post('/projects/<uuid:project_id>/notes')
@require()
def project_note(project_id):
    row = get(Project, project_id)
    service.log_event(row, 'note', payload(NoteSchema)['text'], g.user.id)
    db.session.commit()
    return {'ok': True}, 201


# ---------- files ----------
@bp.post('/projects/<uuid:project_id>/files')
@require()
@limiter.limit('60 per hour')
def file_upload(project_id):
    project = get(Project, project_id)
    upload = request.files.get('file')
    if not upload:
        raise APIError('Envie um arquivo.')
    meta = FileMetaSchema().load({k: v for k, v in request.form.items() if k in ('title', 'kind', 'note') and v != ''})
    name, extension, content = service.check_upload(upload)
    replaces = request.form.get('replaces_group_id')
    group_id, version, title, kind = None, 1, meta.get('title') or name.rsplit('.', 1)[0][:180], meta.get('kind', 'layout')
    if replaces:
        latest = query(ProjectFile).filter_by(project_id=project.id, group_id=replaces).order_by(ProjectFile.version.desc()).first()
        if not latest:
            raise APIError('Arquivo original não encontrado.', 404)
        group_id, version, title, kind = latest.group_id, latest.version + 1, meta.get('title') or latest.title, meta.get('kind') or latest.kind
    key = service.save_bytes(g.workspace_id, project.id, extension, content)
    try:
        row = add(ProjectFile, {'project_id': project.id, 'group_id': group_id or '', 'version': version, 'kind': kind, 'title': title, 'filename': name[:255],
                                'mimetype': service.FILE_TYPES[extension][0], 'size': len(content), 'storage_key': key, 'note': meta.get('note'), 'uploaded_by': g.user.id})
        row.group_id = group_id or row.id
        service.log_event(project, 'file', f'{"Nova versão (v" + str(version) + ")" if version > 1 else "Arquivo"} enviado: “{title}”.', g.user.id)
        db.session.commit()
    except Exception:
        db.session.rollback()
        service.delete_bytes(key)
        raise
    return file_dict(row), 201


def file_response(row, inline):
    path = service.storage_path(row.storage_key)
    if not path.is_file():
        raise APIError('Arquivo indisponível.', 404)
    ext = row.filename.rsplit('.', 1)[-1].lower() if '.' in row.filename else ''
    show = inline and service.FILE_TYPES.get(ext, ('', False))[1]
    response = send_file(path, mimetype=row.mimetype, as_attachment=not show, download_name=row.filename, max_age=0)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox"
    response.headers['Cache-Control'] = 'private, no-store'
    return response


@bp.get('/projects/<uuid:project_id>/files/<uuid:file_id>/download')
@require()
def file_download(project_id, file_id):
    get(Project, project_id)
    row = query(ProjectFile).filter_by(id=str(file_id), project_id=str(project_id)).first()
    if not row:
        raise APIError('Arquivo não encontrado.', 404)
    return file_response(row, request.args.get('inline') == '1')


@bp.patch('/projects/<uuid:project_id>/files/<uuid:file_id>')
@require()
def file_update(project_id, file_id):
    get(Project, project_id)
    row = query(ProjectFile).filter_by(id=str(file_id), project_id=str(project_id)).first()
    if not row:
        raise APIError('Arquivo não encontrado.', 404)
    data = payload(FileMetaSchema, partial=True)
    for sibling in query(ProjectFile).filter_by(project_id=row.project_id, group_id=row.group_id).all():
        for key in ('title', 'kind'):
            if key in data:
                setattr(sibling, key, data[key])
    if 'note' in data:
        row.note = data['note']
    db.session.commit()
    return file_dict(row)


@bp.delete('/projects/<uuid:project_id>/files/<uuid:file_id>')
@require()
def file_delete(project_id, file_id):
    project = get(Project, project_id)
    row = query(ProjectFile).filter_by(id=str(file_id), project_id=str(project_id)).first()
    if not row:
        raise APIError('Arquivo não encontrado.', 404)
    if query(ProjectApproval).filter_by(file_id=row.id).first():
        row.archived = True  # Approval history keeps pointing at what the client saw.
    else:
        db.session.delete(row)
        service.delete_bytes(row.storage_key)
    service.log_event(project, 'file', f'Arquivo removido: “{row.title}” (v{row.version}).', g.user.id)
    db.session.commit()
    return '', 204


# ---------- approvals (team side) ----------
def new_token(row, days):
    token = secrets.token_urlsafe(32)
    row.token_hash = hashlib.sha256(token.encode()).hexdigest()
    row.expires_at = now() + timedelta(days=days)
    return token


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
    row = add(ProjectApproval, {'project_id': project.id, 'file_id': file.id if file else None, 'title': data['title'], 'message': data.get('message'),
                                'channel': data['channel'], 'requested_by': g.user.id})
    token = new_token(row, data['expires_days']) if data['channel'] == 'public' else None
    service.log_event(project, 'approval', f'Aprovação solicitada: “{data["title"]}”' + (f' (v{file.version})' if file else '') + '.', g.user.id)
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
    token = new_token(row, 30)
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


def record_decision(project, row, decision, name, comment, ip, channel, user_id=None):
    row.status, row.decided_at, row.decided_by, row.decision_comment, row.decided_ip = decision, now(), name[:150], comment, (ip or '')[:64] or None
    row.channel = channel
    row.token_hash = None  # The link is single-use.
    label = 'aprovou' if decision == 'approved' else 'pediu ajustes em'
    service.log_event(project, 'approval', f'{name} {label} “{row.title}”' + (f': {comment[:200]}' if comment else '.'), user_id)


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
    record_decision(project, row, data['decision'], data['name'], data.get('comment'), None, 'internal', g.user.id)
    db.session.commit()
    return {'ok': True}


# ---------- approvals (client side, no login) ----------
def by_token(token):
    row = ProjectApproval.query.filter_by(token_hash=hashlib.sha256(token.encode()).hexdigest()).first()
    if not row or row.status == 'cancelled':
        raise APIError('Link inválido ou expirado.', 404)
    return row


@bp.get('/public/approvals/<token>')
@limiter.limit('60 per minute')
def public_approval(token):
    row = by_token(token)
    project = db.session.get(Project, row.project_id)
    workspace = db.session.get(Workspace, row.workspace_id)
    file = db.session.get(ProjectFile, row.file_id) if row.file_id else None
    expired = bool(row.expires_at and row.expires_at <= now())
    return {'title': row.title, 'message': row.message, 'project': project.title, 'company': workspace.name,
            'status': 'expired' if expired and row.status == 'pending' else row.status,
            'file': {'name': file.title, 'version': file.version, 'mimetype': file.mimetype, 'inline': file_dict(file)['inline']} if file else None}


@bp.get('/public/approvals/<token>/file')
@limiter.limit('60 per minute')
def public_approval_file(token):
    row = by_token(token)
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
    row = ProjectApproval.query.filter_by(token_hash=hashlib.sha256(token.encode()).hexdigest()).with_for_update().first()
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
    record_decision(project, row, data['decision'], data['name'], data.get('comment'),
                    request.headers.get('X-Client-IP') or request.remote_addr, 'public')
    db.session.commit()
    return {'message': 'Resposta registrada. Obrigado!', 'status': row.status}
