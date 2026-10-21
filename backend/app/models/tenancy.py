from sqlalchemy import UniqueConstraint

from ..extensions import db
from .base import Base, TenantBase


class Workspace(Base):
    __tablename__ = 'workspaces'
    parent_workspace_id = db.Column(db.String(36), db.ForeignKey('workspaces.id'), index=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    name = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    timezone = db.Column(db.String(80), nullable=False, default='America/Sao_Paulo')


class User(TenantBase):
    """Identity owned by a workspace; agency access is granted separately."""

    __tablename__ = 'users'
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(254), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='member')  # owner | admin | member
    title = db.Column(db.String(80))  # free label, e.g. "Vendedor", "SDR"
    active = db.Column(db.Boolean, default=True, nullable=False)
    token_version = db.Column(db.Integer, default=0, nullable=False)
    __table_args__ = (UniqueConstraint('workspace_id', 'email'),)


class WorkspaceAccess(Base):
    __tablename__ = 'workspace_access'
    workspace_id = db.Column(db.String(36), db.ForeignKey('workspaces.id'), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False, default='member')
    __table_args__ = (UniqueConstraint('workspace_id', 'user_id'),)


class AuditLog(TenantBase):
    __tablename__ = 'audit_logs'
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    action = db.Column(db.String(80), nullable=False)
    resource = db.Column(db.String(80), nullable=False)
    resource_id = db.Column(db.String(36))
    details = db.Column(db.JSON, nullable=False, default=dict)
