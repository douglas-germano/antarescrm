"""Resolve account access from current database state on every authenticated request."""
from .extensions import db
from .models import Workspace, WorkspaceAccess, User


def workspace_role(user, workspace):
    if not user or not user.active or not workspace or not workspace.active:
        return None
    home = db.session.get(Workspace, user.workspace_id)
    if not home or not home.active:
        return None
    if workspace.id == user.workspace_id:
        return user.role if user.role in ('owner', 'admin', 'member') else None
    # Client identities cannot move to parents or siblings, even with a malformed grant.
    if home.parent_workspace_id or workspace.parent_workspace_id != home.id:
        return None
    if user.role in ('owner', 'admin'):
        return 'admin'
    grant = WorkspaceAccess.query.filter_by(workspace_id=workspace.id, user_id=user.id).first()
    return grant.role if grant and grant.role in ('admin', 'member') else None


def accessible_workspaces(user):
    home = db.session.get(Workspace, user.workspace_id)
    candidates = [home] if home else []
    if home and not home.parent_workspace_id:
        candidates += Workspace.query.filter_by(parent_workspace_id=home.id, active=True).order_by(Workspace.name).all()
    return [(ws, workspace_role(user, ws)) for ws in candidates if workspace_role(user, ws)]


def account_users(workspace_id):
    workspace = db.session.get(Workspace, workspace_id)
    rows = User.query.filter_by(workspace_id=workspace_id).all()
    if workspace.parent_workspace_id:
        staff = User.query.filter_by(workspace_id=workspace.parent_workspace_id, active=True).all()
        rows += [user for user in staff if workspace_role(user, workspace)]
    return sorted(rows, key=lambda u: u.name.casefold())
