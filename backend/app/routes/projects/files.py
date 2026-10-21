from flask import g, request, send_file

from ...common import APIError, add, get, payload, query, require
from ...extensions import db, limiter
from ...models import (
    Project,
    ProjectApproval,
    ProjectFile,
)
from ...schemas import FileMetaSchema
from ...services import projects as service

# ---------- schemas ----------
from . import bp
from .serializers import file_dict


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
    group_id, version, title, kind = (
        None,
        1,
        meta.get('title') or name.rsplit('.', 1)[0][:180],
        meta.get('kind', 'layout'),
    )
    if replaces:
        latest = (
            query(ProjectFile)
            .filter_by(project_id=project.id, group_id=replaces)
            .order_by(ProjectFile.version.desc())
            .first()
        )
        if not latest:
            raise APIError('Arquivo original não encontrado.', 404)
        group_id, version, title, kind = (
            latest.group_id,
            latest.version + 1,
            meta.get('title') or latest.title,
            meta.get('kind') or latest.kind,
        )
    key = service.save_bytes(g.workspace_id, project.id, extension, content)
    try:
        row = add(
            ProjectFile,
            {
                'project_id': project.id,
                'group_id': group_id or '',
                'version': version,
                'kind': kind,
                'title': title,
                'filename': name[:255],
                'mimetype': service.FILE_TYPES[extension][0],
                'size': len(content),
                'storage_key': key,
                'note': meta.get('note'),
                'uploaded_by': g.user.id,
            },
        )
        row.group_id = group_id or row.id
        service.log_event(
            project,
            'file',
            f'{"Nova versão (v" + str(version) + ")" if version > 1 else "Arquivo"} enviado: “{title}”.',
            g.user.id,
        )
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
    response.headers['Content-Security-Policy'] = (
        "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox"
    )
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
