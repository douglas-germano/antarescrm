from flask import g
from sqlalchemy import func

from ...access import account_users
from ...common import query
from ...models import (
    Company,
    Contact,
    ProjectApproval,
    ProjectFile,
    ProjectStage,
    now,
)
from ...services import projects as service

# ---------- schemas ----------


def stage_dict(stage):
    return {
        'id': stage.id,
        'name': stage.name,
        'color': stage.color,
        'is_final': stage.is_final,
        'position': stage.position,
    }


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
    data.update(
        {
            'contact_name': contact.name if contact else None,
            'company_name': lookups['companies'].get(project.company_id).name
            if project.company_id in lookups['companies']
            else None,
            'owner_name': lookups['users'].get(project.owner_id),
            'stage': stage_dict(lookups['stages'][project.stage_id]) if project.stage_id in lookups['stages'] else None,
            'files_count': lookups['files'].get(project.id, 0),
            'pending_approvals': lookups['approvals'].get(project.id, 0),
        }
    )
    return data


def lookups_for(rows):
    ids = [r.id for r in rows]

    return {
        'contacts': {
            c.id: c for c in query(Contact).filter(Contact.id.in_([r.contact_id for r in rows if r.contact_id])).all()
        }
        if rows
        else {},
        'companies': {
            c.id: c for c in query(Company).filter(Company.id.in_([r.company_id for r in rows if r.company_id])).all()
        }
        if rows
        else {},
        'users': {u.id: u.name for u in account_users(g.workspace_id)},
        'stages': {s.id: s for s in query(ProjectStage).all()},
        'files': dict(
            query(ProjectFile)
            .filter(ProjectFile.project_id.in_(ids), ProjectFile.archived.is_(False))
            .with_entities(ProjectFile.project_id, func.count(func.distinct(ProjectFile.group_id)))
            .group_by(ProjectFile.project_id)
            .all()
        )
        if ids
        else {},
        'approvals': dict(
            query(ProjectApproval)
            .filter(ProjectApproval.project_id.in_(ids), ProjectApproval.status == 'pending')
            .with_entities(ProjectApproval.project_id, func.count(ProjectApproval.id))
            .group_by(ProjectApproval.project_id)
            .all()
        )
        if ids
        else {},
    }
