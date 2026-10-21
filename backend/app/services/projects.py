"""Client projects: stages, creation from won deals, file storage and the timeline."""

import contextlib
import hashlib
import secrets
import uuid
from datetime import timedelta
from pathlib import Path

from flask import current_app

from ..common import APIError, get, user_ref
from ..extensions import db
from ..models import Company, Contact, Opportunity, Project, ProjectApproval, ProjectEvent, ProjectStage, now
from .domains import ensure_scope

DEFAULT_STAGES = [
    ('Briefing', '#6b6e71', False),
    ('Criação', '#25282b', False),
    ('Aprovação', '#c77d00', False),
    ('Publicação', '#e60000', False),
    ('Relatório', '#2e7d52', True),
]

# Extension → (mimetype, can be shown inline in the browser). SVG and HTML are deliberately absent.
FILE_TYPES = {
    'png': ('image/png', True),
    'jpg': ('image/jpeg', True),
    'jpeg': ('image/jpeg', True),
    'gif': ('image/gif', True),
    'webp': ('image/webp', True),
    'pdf': ('application/pdf', True),
    'doc': ('application/msword', False),
    'docx': ('application/vnd.openxmlformats-officedocument.wordprocessingml.document', False),
    'xls': ('application/vnd.ms-excel', False),
    'xlsx': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', False),
    'ppt': ('application/vnd.ms-powerpoint', False),
    'pptx': ('application/vnd.openxmlformats-officedocument.presentationml.presentation', False),
    'zip': ('application/zip', False),
    'psd': ('image/vnd.adobe.photoshop', False),
    'ai': ('application/pdf', False),
    'mp4': ('video/mp4', True),
    'mov': ('video/quicktime', False),
    'txt': ('text/plain', False),
    'csv': ('text/csv', False),
}
MAGIC = {
    'psd': [b'8BPS'],
    'ai': [b'%PDF'],
    'png': [b'\x89PNG'],
    'jpg': [b'\xff\xd8\xff'],
    'jpeg': [b'\xff\xd8\xff'],
    'gif': [b'GIF8'],
    'webp': [b'RIFF'],
    'pdf': [b'%PDF'],
    'zip': [b'PK'],
    'docx': [b'PK'],
    'xlsx': [b'PK'],
    'pptx': [b'PK'],
}


def ensure_stages(workspace_id):
    """Every account starts with the standard workflow; it can be edited in Configurações → Projetos."""
    if ProjectStage.query.filter_by(workspace_id=workspace_id).first():
        return
    for position, (name, color, final) in enumerate(DEFAULT_STAGES):
        db.session.add(
            ProjectStage(workspace_id=workspace_id, name=name, position=position, color=color, is_final=final)
        )
    db.session.flush()


def first_stage(workspace_id):
    ensure_stages(workspace_id)
    return ProjectStage.query.filter_by(workspace_id=workspace_id).order_by(ProjectStage.position).first()


def log_event(project, kind, text, user_id=None):
    db.session.add(
        ProjectEvent(
            workspace_id=project.workspace_id, project_id=project.id, kind=kind, text=text[:500], user_id=user_id
        )
    )


def create_from_deal(deal, user_id=None):
    """One project per deal. Safe to call repeatedly; returns the existing project when there is one."""
    existing = Project.query.filter_by(workspace_id=deal.workspace_id, opportunity_id=deal.id).first()
    if existing:
        return existing
    stage = first_stage(deal.workspace_id)
    project = Project(
        workspace_id=deal.workspace_id,
        opportunity_id=deal.id,
        contact_id=deal.contact_id,
        company_id=deal.company_id,
        owner_id=deal.owner_id,
        stage_id=stage.id,
        title=deal.title,
        description=deal.description,
        amount=deal.amount,
        start_date=now().date(),
    )
    db.session.add(project)
    db.session.flush()
    log_event(project, 'created', 'Projeto criado a partir do negócio “' + deal.title + '”.', user_id)
    return project


# ---- file storage ----
def storage_root():
    root = Path(current_app.config['PROJECT_FILES_DIR'])
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def storage_path(key):
    path = (storage_root() / key).resolve()
    if storage_root() not in path.parents:
        raise APIError('Arquivo inválido.', 400)
    return path


def check_upload(file):
    """Validates the extension and header; the stored mimetype comes from our table, never from the client."""
    name = (file.filename or '').strip()
    extension = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if extension not in FILE_TYPES:
        raise APIError(
            'Tipo de arquivo não permitido. Use imagens, PDF, vídeo MP4, documentos do Office, ZIP ou arquivos PSD/AI.',
            422,
        )
    content = file.read(current_app.config['PROJECT_FILE_MAX_BYTES'] + 1)
    if not content:
        raise APIError('O arquivo está vazio.', 422)
    if len(content) > current_app.config['PROJECT_FILE_MAX_BYTES']:
        raise APIError('O arquivo deve ter até 14 MB.', 413)
    if (
        extension in ('mp4', 'mov')
        and content[4:8] != b'ftyp'
        and content[4:8] != b'moov'
        and content[4:8] != b'wide'
        and content[4:8] != b'mdat'
    ):
        raise APIError('O conteúdo do arquivo não corresponde à extensão.', 422)
    if extension in MAGIC and not any(content.startswith(sig) for sig in MAGIC[extension]):
        raise APIError('O conteúdo do arquivo não corresponde à extensão.', 422)
    return name, extension, content


def save_bytes(workspace_id, project_id, extension, content):
    key = f'{workspace_id}/{project_id}/{uuid.uuid4().hex}.{extension}'
    path = storage_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return key


def delete_bytes(key):
    with contextlib.suppress(OSError, APIError):
        storage_path(key).unlink(missing_ok=True)


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
    log_event(
        project, 'stage', f'Etapa alterada de “{previous.name if previous else "—"}” para “{stage.name}”.', user_id
    )
    if stage.is_final and project.status == 'active':
        project.status, project.completed_at = 'done', now()
        log_event(project, 'status', 'Projeto concluído.', user_id)
    elif not stage.is_final and project.status == 'done':
        project.status, project.completed_at = 'active', None
        log_event(project, 'status', 'Projeto reaberto.', user_id)


def new_token(row, days):
    token = secrets.token_urlsafe(32)
    row.token_hash = hashlib.sha256(token.encode()).hexdigest()
    row.expires_at = now() + timedelta(days=days)
    return token


def record_decision(project, row, decision, name, comment, ip, channel, user_id=None):
    row.status, row.decided_at, row.decided_by, row.decision_comment, row.decided_ip = (
        decision,
        now(),
        name[:150],
        comment,
        (ip or '')[:64] or None,
    )
    row.channel = channel
    row.token_hash = None  # The link is single-use.
    label = 'aprovou' if decision == 'approved' else 'pediu ajustes em'
    log_event(
        project, 'approval', f'{name} {label} “{row.title}”' + (f': {comment[:200]}' if comment else '.'), user_id
    )


def by_token(token):
    row = ProjectApproval.query.filter_by(token_hash=hashlib.sha256(token.encode()).hexdigest()).first()
    if not row or row.status == 'cancelled':
        raise APIError('Link inválido ou expirado.', 404)
    ensure_scope(row.workspace_id)
    return row
