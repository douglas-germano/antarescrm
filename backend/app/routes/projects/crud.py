from flask import g, request

from ...common import audit, commit, get, page, payload, query, require
from ...extensions import db
from ...models import (
    Contact,
    Opportunity,
    Project,
    ProjectApproval,
    ProjectEvent,
    ProjectFile,
)
from ...schemas import NoteSchema, ProjectSchema
from ...services import projects as service

# ---------- schemas ----------
from . import bp
from .serializers import approval_dict, file_dict, lookups_for, project_row


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
        q = q.outerjoin(Contact, Contact.id == Project.contact_id).filter(
            db.or_(Project.title.ilike(like), Contact.name.ilike(like))
        )
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
    row = service.create_project(payload(ProjectSchema, partial=True), g.workspace_id, g.user.id)
    return commit(row, 201)


@bp.get('/projects/<uuid:project_id>')
@require()
def project_detail(project_id):
    row = get(Project, project_id)
    look = lookups_for([row])
    data = project_row(row, look)
    deal = db.session.get(Opportunity, row.opportunity_id) if row.opportunity_id else None
    data['deal'] = (
        {
            'id': deal.id,
            'title': deal.title,
            'amount': format(deal.amount, '.2f'),
            'status': deal.status,
            'expected_close_date': deal.expected_close_date.isoformat() if deal.expected_close_date else None,
            'closed_at': deal.closed_at.isoformat() if deal.closed_at else None,
        }
        if deal and deal.workspace_id == g.workspace_id
        else None
    )
    contact = look['contacts'].get(row.contact_id)
    data['contact'] = (
        {'id': contact.id, 'name': contact.name, 'phone': contact.phone, 'email': contact.email} if contact else None
    )
    files = query(ProjectFile).filter_by(project_id=row.id, archived=False).order_by(ProjectFile.version).all()
    groups = {}
    for file in files:
        groups.setdefault(file.group_id, []).append(file)
    data['files'] = [
        {
            'group_id': gid,
            'title': versions[-1].title,
            'kind': versions[-1].kind,
            'latest': file_dict(versions[-1]),
            'versions': [file_dict(v) for v in reversed(versions)],
        }
        for gid, versions in sorted(groups.items(), key=lambda kv: kv[1][-1].created_at, reverse=True)
    ]
    by_id = {fl.id: fl for fl in query(ProjectFile).filter_by(project_id=row.id).all()}
    data['approvals'] = [
        approval_dict(a, by_id)
        for a in query(ProjectApproval).filter_by(project_id=row.id).order_by(ProjectApproval.created_at.desc()).all()
    ]
    events = query(ProjectEvent).filter_by(project_id=row.id).order_by(ProjectEvent.created_at.desc()).limit(200).all()
    names = look['users']
    data['events'] = [{**e.to_dict(), 'user_name': names.get(e.user_id)} for e in events]
    return data


@bp.patch('/projects/<uuid:project_id>')
@require()
def project_update(project_id):
    row = get(Project, project_id, lock=True)
    data = payload(ProjectSchema, partial=True)
    return commit(service.modify_project(row, data, g.user.id))


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
