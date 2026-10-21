from sqlalchemy import UniqueConstraint

from ..extensions import db
from .base import TenantBase, UTCDateTime


class ProjectStage(TenantBase):
    """Configurable steps of the client-project workflow (e.g. Briefing, Criação, Aprovação, Publicação)."""

    __tablename__ = 'project_stages'
    name = db.Column(db.String(80), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    color = db.Column(db.String(7), nullable=False, default='#25282b')
    is_final = db.Column(db.Boolean, nullable=False, default=False)  # reaching it completes the project
    __table_args__ = (UniqueConstraint('workspace_id', 'name', name='uq_project_stage_name'),)


class Project(TenantBase):
    __tablename__ = 'projects'
    opportunity_id = db.Column(db.String(36), db.ForeignKey('opportunities.id'), index=True)
    contact_id = db.Column(db.String(36), db.ForeignKey('contacts.id'), index=True)
    company_id = db.Column(db.String(36), db.ForeignKey('companies.id'), index=True)
    owner_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    stage_id = db.Column(db.String(36), db.ForeignKey('project_stages.id'), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text)
    amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default='active')  # active | done | cancelled
    start_date = db.Column(db.Date)
    due_date = db.Column(db.Date)
    completed_at = db.Column(UTCDateTime())
    __table_args__ = (UniqueConstraint('workspace_id', 'opportunity_id', name='uq_project_opportunity'),)


class ProjectFile(TenantBase):
    """A creative (art, video) or document. Re-uploading creates a new version in the same group; old versions are kept."""

    __tablename__ = 'project_files'
    project_id = db.Column(db.String(36), db.ForeignKey('projects.id'), nullable=False, index=True)
    group_id = db.Column(db.String(36), nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    kind = db.Column(db.String(20), nullable=False, default='layout')  # layout | document | other
    title = db.Column(db.String(180), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    mimetype = db.Column(db.String(150), nullable=False)
    size = db.Column(db.Integer, nullable=False, default=0)
    storage_key = db.Column(db.String(300), nullable=False)
    note = db.Column(db.Text)
    uploaded_by = db.Column(db.String(36), db.ForeignKey('users.id'))
    archived = db.Column(db.Boolean, nullable=False, default=False)


class ProjectApproval(TenantBase):
    """A request for the client to approve something, answered through a public link or registered by the team."""

    __tablename__ = 'project_approvals'
    project_id = db.Column(db.String(36), db.ForeignKey('projects.id'), nullable=False, index=True)
    file_id = db.Column(db.String(36), db.ForeignKey('project_files.id'))
    title = db.Column(db.String(180), nullable=False)
    message = db.Column(db.Text)
    status = db.Column(
        db.String(20), nullable=False, default='pending'
    )  # pending | approved | changes_requested | cancelled
    channel = db.Column(db.String(20), nullable=False, default='public')  # public | internal
    token_hash = db.Column(db.String(64), unique=True)
    expires_at = db.Column(UTCDateTime())
    requested_by = db.Column(db.String(36), db.ForeignKey('users.id'))
    decided_at = db.Column(UTCDateTime())
    decided_by = db.Column(db.String(150))
    decided_ip = db.Column(db.String(64))
    decision_comment = db.Column(db.Text)


class ProjectEvent(TenantBase):
    __tablename__ = 'project_events'
    project_id = db.Column(db.String(36), db.ForeignKey('projects.id'), nullable=False, index=True)
    kind = db.Column(db.String(30), nullable=False)
    text = db.Column(db.String(500), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'))
