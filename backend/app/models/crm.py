from sqlalchemy import CheckConstraint, UniqueConstraint

from ..extensions import db
from .base import TenantBase, UTCDateTime


class Company(TenantBase):
    tags = db.Column(db.JSON, nullable=False, default=list)
    custom_fields = db.Column(db.JSON, nullable=False, default=dict)
    __tablename__ = 'companies'
    name = db.Column(db.String(180), nullable=False)
    document = db.Column(db.String(20))  # CNPJ
    website = db.Column(db.String(255))
    email = db.Column(db.String(254))
    phone = db.Column(db.String(30))
    industry = db.Column(db.String(120))
    address = db.Column(db.Text)
    notes = db.Column(db.Text)
    archived = db.Column(db.Boolean, default=False, nullable=False)


class Contact(TenantBase):
    tags = db.Column(db.JSON, nullable=False, default=list)
    custom_fields = db.Column(db.JSON, nullable=False, default=dict)
    __tablename__ = 'contacts'
    company_id = db.Column(db.String(36), db.ForeignKey('companies.id'), index=True)
    owner_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    name = db.Column(db.String(180), nullable=False)
    email = db.Column(db.String(254))
    phone = db.Column(db.String(30))
    position = db.Column(db.String(120))
    source = db.Column(db.String(100))
    notes = db.Column(db.Text)
    archived = db.Column(db.Boolean, default=False, nullable=False)


class Pipeline(TenantBase):
    __tablename__ = 'pipelines'
    name = db.Column(db.String(150), nullable=False)
    __table_args__ = (UniqueConstraint('workspace_id', 'name'),)


class PipelineStage(TenantBase):
    pipeline_id = db.Column(db.String(36), db.ForeignKey('pipelines.id'), index=True)
    __tablename__ = 'pipeline_stages'
    name = db.Column(db.String(80), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    color = db.Column(db.String(7), nullable=False, default='#397567')
    probability = db.Column(db.Integer)  # win chance in %, used for weighted forecasts; null = not set
    __table_args__ = (UniqueConstraint('workspace_id', 'pipeline_id', 'name', name='uq_stage_pipeline_name'),)


class Opportunity(TenantBase):
    __tablename__ = 'opportunities'
    contact_id = db.Column(db.String(36), db.ForeignKey('contacts.id'), index=True)
    company_id = db.Column(db.String(36), db.ForeignKey('companies.id'), index=True)
    stage_id = db.Column(db.String(36), db.ForeignKey('pipeline_stages.id'), nullable=False)
    owner_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text)
    amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default='open')  # open | won | lost
    expected_close_date = db.Column(db.Date)
    closed_at = db.Column(UTCDateTime())
    loss_reason = db.Column(db.Text)
    __table_args__ = (CheckConstraint('amount >= 0'),)


class StageHistory(TenantBase):
    __tablename__ = 'stage_history'
    opportunity_id = db.Column(db.String(36), db.ForeignKey('opportunities.id'), nullable=False)
    from_stage_id = db.Column(db.String(36), db.ForeignKey('pipeline_stages.id'))
    to_stage_id = db.Column(db.String(36), db.ForeignKey('pipeline_stages.id'), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)


class Activity(TenantBase):
    """Interactions and scheduled touchpoints (call, meeting, e-mail, note, follow-up)."""

    __tablename__ = 'activities'
    opportunity_id = db.Column(db.String(36), db.ForeignKey('opportunities.id'), index=True)
    contact_id = db.Column(db.String(36), db.ForeignKey('contacts.id'), index=True)
    company_id = db.Column(db.String(36), db.ForeignKey('companies.id'), index=True)
    owner_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    title = db.Column(db.String(180), nullable=False)
    kind = db.Column(db.String(20), default='follow_up', nullable=False)
    scheduled_at = db.Column(UTCDateTime(), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    notes = db.Column(db.Text)


class Task(TenantBase):
    __tablename__ = 'tasks'
    assignee_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    contact_id = db.Column(db.String(36), db.ForeignKey('contacts.id'), index=True)
    company_id = db.Column(db.String(36), db.ForeignKey('companies.id'), index=True)
    opportunity_id = db.Column(db.String(36), db.ForeignKey('opportunities.id'), index=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default='todo')  # todo | doing | done | cancelled
    priority = db.Column(db.String(20), nullable=False, default='medium')
    due_date = db.Column(db.Date)
    completed_at = db.Column(UTCDateTime())


class SavedContactView(TenantBase):
    __tablename__ = 'saved_contact_views'
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    filters = db.Column(db.JSON, nullable=False)
    __table_args__ = (UniqueConstraint('workspace_id', 'user_id', 'name'),)
