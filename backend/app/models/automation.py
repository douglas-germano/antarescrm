from sqlalchemy import UniqueConstraint

from ..extensions import db
from .base import Base, TenantBase, UTCDateTime, now


class LeadForm(TenantBase):
    fields = db.Column(db.JSON, nullable=False, default=list)
    brand_name = db.Column(db.String(120), nullable=False, default='')
    accent_color = db.Column(db.String(7), nullable=False, default='#7542c6')
    design = db.Column(db.JSON, nullable=False, default=dict)
    settings = db.Column(db.JSON, nullable=False, default=dict)
    __tablename__ = 'lead_forms'
    name = db.Column(db.String(150), nullable=False)
    headline = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False, default='')
    success_message = db.Column(
        db.String(500), nullable=False, default='Recebemos sua solicitação. Nossa equipe entrará em contato.'
    )
    stage_id = db.Column(db.String(36), db.ForeignKey('pipeline_stages.id'), nullable=False)
    source = db.Column(db.String(100), nullable=False, default='Formulário')
    active = db.Column(db.Boolean, nullable=False, default=False)


class FormSubmission(TenantBase):
    answers = db.Column(db.JSON, nullable=False, default=dict)
    attribution = db.Column(db.JSON, nullable=False, default=dict)
    __tablename__ = 'form_submissions'
    form_id = db.Column(db.String(36), db.ForeignKey('lead_forms.id'), nullable=False, index=True)
    submission_key = db.Column(db.String(36), nullable=False)
    contact_id = db.Column(db.String(36), db.ForeignKey('contacts.id'), nullable=False)
    opportunity_id = db.Column(db.String(36), db.ForeignKey('opportunities.id'), nullable=False)
    consent_text = db.Column(db.String(255), nullable=False)
    __table_args__ = (UniqueConstraint('form_id', 'submission_key'),)


class AutomationRule(TenantBase):
    stop_on_reply = db.Column(db.Boolean, nullable=False, default=False)
    conditions = db.Column(db.JSON, nullable=False, default=dict)
    required_tag = db.Column(db.String(80))
    actions = db.Column(db.JSON, nullable=False, default=list)
    __tablename__ = 'automation_rules'
    name = db.Column(db.String(150), nullable=False)
    event = db.Column(db.String(40), nullable=False)
    source = db.Column(db.String(100))
    task_title = db.Column(db.String(180), nullable=False)
    due_days = db.Column(db.Integer, nullable=False, default=0)
    assignee_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    active = db.Column(db.Boolean, nullable=False, default=False)


class AutomationRun(TenantBase):
    config_snapshot = db.Column(db.JSON, nullable=False, default=dict)
    __tablename__ = 'automation_runs'
    rule_id = db.Column(db.String(36), db.ForeignKey('automation_rules.id'), nullable=False)
    event_key = db.Column(db.String(100), nullable=False)
    contact_id = db.Column(db.String(36), db.ForeignKey('contacts.id'), nullable=False)
    task_id = db.Column(db.String(36), db.ForeignKey('tasks.id', ondelete='SET NULL'))
    status = db.Column(db.String(20), nullable=False)
    detail = db.Column(db.String(500), nullable=False)
    __table_args__ = (UniqueConstraint('rule_id', 'event_key'),)


class AutomationJob(TenantBase):
    __tablename__ = 'automation_jobs'
    run_id = db.Column(db.String(36), db.ForeignKey('automation_runs.id'), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False)
    action = db.Column(db.JSON, nullable=False)
    scheduled_at = db.Column(UTCDateTime(), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='pending')
    result_id = db.Column(db.String(36))
    detail = db.Column(db.String(500))
    __table_args__ = (UniqueConstraint('run_id', 'position'),)


class WorkerHeartbeat(Base):
    dispatch_enabled = db.Column(db.Boolean, nullable=False, default=False)
    __tablename__ = 'worker_heartbeats'
    name = db.Column(db.String(80), unique=True, nullable=False)
    last_seen_at = db.Column(UTCDateTime(), nullable=False, default=now)
    last_success_at = db.Column(UTCDateTime())
    error = db.Column(db.Boolean, nullable=False, default=False)
