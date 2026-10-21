from flask import Blueprint, g
from marshmallow import fields as f
from marshmallow import validate
from werkzeug.security import generate_password_hash

from ..access import accessible_workspaces, workspace_role
from ..common import APIError, audit, page, payload, query, require, validate_timezone
from ..extensions import db
from ..models import AuditLog, PipelineStage, User, Workspace, WorkspaceAccess
from ..schemas import RegisterSchema, StrictSchema, WorkspaceSchema, choice, ref
from .auth import DEFAULT_STAGES, tokens

bp = Blueprint('agency', __name__)


class SwitchSchema(StrictSchema):
    workspace_id = ref(required=True)


class AccountSchema(RegisterSchema):
    timezone = f.String(validate=validate.Length(min=1, max=80), load_default='America/Cuiaba')


class AccountUpdateSchema(WorkspaceSchema):
    active = f.Boolean()


class AccessSchema(StrictSchema):
    user_id = ref(required=True)
    role = choice('admin member', required=True)


def agency_home():
    home = db.session.get(Workspace, g.user.workspace_id)
    if home.parent_workspace_id or g.workspace_id != home.id or g.user.role not in ('owner', 'admin'):
        raise APIError('A administração de clientes pertence à agência.', 403)
    return home


def client_account(identifier):
    home = agency_home()
    row = Workspace.query.filter_by(id=str(identifier), parent_workspace_id=home.id).first()
    if not row:
        raise APIError('Conta não encontrada.', 404)
    return row


@bp.get('/auth/workspaces')
@require()
def workspaces():
    return {'items': [dict(ws.to_dict(), effective_role=role) for ws, role in accessible_workspaces(g.user)]}


@bp.post('/auth/switch')
@require()
def switch():
    data = payload(SwitchSchema)
    workspace = db.session.get(Workspace, data['workspace_id'])
    if not workspace_role(g.user, workspace):
        raise APIError('Conta não encontrada.', 404)
    audit('switch_account', workspace)
    db.session.commit()
    return tokens(g.user, workspace.id)


@bp.get('/agency/accounts')
@require('owner', 'admin')
def accounts():
    home = agency_home()
    return page(Workspace.query.filter_by(parent_workspace_id=home.id).order_by(Workspace.name))


@bp.post('/agency/accounts')
@require('owner', 'admin')
def account_create():
    home = agency_home()
    data = payload(AccountSchema)
    validate_timezone(data['timezone'])
    workspace = Workspace(
        name=data['workspace_name'], slug=data['slug'], timezone=data['timezone'], parent_workspace_id=home.id
    )
    db.session.add(workspace)
    db.session.flush()
    owner = User(
        workspace_id=workspace.id,
        name=data['name'],
        email=data['email'].lower(),
        password_hash=generate_password_hash(data['password']),
        role='owner',
    )
    db.session.add(owner)
    for position, name in enumerate(DEFAULT_STAGES):
        db.session.add(PipelineStage(workspace_id=workspace.id, name=name, position=position))
    audit('create_client_account', workspace)
    db.session.commit()
    return workspace.to_dict(), 201


@bp.patch('/agency/accounts/<uuid:account_id>')
@require('owner', 'admin')
def account_update(account_id):
    workspace = client_account(account_id)
    data = payload(AccountUpdateSchema)
    if 'timezone' in data:
        validate_timezone(data['timezone'])
    for key, value in data.items():
        setattr(workspace, key, value)
    audit('update_client_account', workspace, {'fields': list(data)})
    db.session.commit()
    return workspace.to_dict()


@bp.get('/agency/accounts/<uuid:account_id>/access')
@require('owner', 'admin')
def access_list(account_id):
    workspace = client_account(account_id)
    grants = WorkspaceAccess.query.filter_by(workspace_id=workspace.id).all()
    return {'items': [dict(row.to_dict(), user_name=db.session.get(User, row.user_id).name) for row in grants]}


@bp.post('/agency/accounts/<uuid:account_id>/access')
@require('owner', 'admin')
def access_save(account_id):
    workspace = client_account(account_id)
    data = payload(AccessSchema)
    user = User.query.filter_by(id=data['user_id'], workspace_id=g.user.workspace_id, active=True).first()
    if not user or user.role != 'member':
        raise APIError('Selecione um membro ativo da agência. Administradores já têm acesso às contas.', 422)
    grant = WorkspaceAccess.query.filter_by(workspace_id=workspace.id, user_id=user.id).first()
    if not grant:
        grant = WorkspaceAccess(workspace_id=workspace.id, user_id=user.id)
        db.session.add(grant)
    grant.role = data['role']
    db.session.flush()
    audit('grant_account_access', grant, {'user_id': user.id, 'role': grant.role})
    db.session.commit()
    return grant.to_dict()


@bp.delete('/agency/accounts/<uuid:account_id>/access/<uuid:user_id>')
@require('owner', 'admin')
def access_revoke(account_id, user_id):
    workspace = client_account(account_id)
    row = WorkspaceAccess.query.filter_by(workspace_id=workspace.id, user_id=str(user_id)).first()
    if not row:
        raise APIError('Acesso não encontrado.', 404)
    audit('revoke_account_access', row, {'user_id': str(user_id)})
    db.session.delete(row)
    db.session.commit()
    return '', 204


@bp.get('/audit-logs')
@require('owner', 'admin')
def audit_logs():

    return page(query(AuditLog).order_by(AuditLog.created_at.desc()))
