import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.types import TypeDecorator, DateTime
from .extensions import db


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Return aware UTC timestamps on both PostgreSQL and SQLite test stores."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).astimezone(timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).astimezone(timezone.utc)
        return value


class Base(db.Model):
    __abstract__ = True
    id = db.Column(db.String(36), primary_key=True, default=uid)
    created_at = db.Column(UTCDateTime(), default=now, nullable=False)
    updated_at = db.Column(UTCDateTime(), default=now, onupdate=now, nullable=False)

    def to_dict(self):
        result = {}
        for column in self.__table__.columns:
            if column.name in ('password_hash', 'token_version'):
                continue
            value = getattr(self, column.name)
            if isinstance(value, Decimal):
                value = format(value, '.2f')
            elif hasattr(value, 'isoformat'):
                value = value.isoformat()
            result[column.name] = value
        return result


class Workspace(Base):
    __tablename__ = 'workspaces'
    parent_workspace_id = db.Column(db.String(36), db.ForeignKey('workspaces.id'), index=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    name = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    timezone = db.Column(db.String(80), nullable=False, default='America/Sao_Paulo')


class TenantBase(Base):
    __abstract__ = True
    workspace_id = db.Column(db.String(36), db.ForeignKey('workspaces.id'), nullable=False, index=True)


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


class WhatsAppConnection(TenantBase):
    __tablename__ = 'whatsapp_connections'
    instance_name = db.Column(db.String(80), unique=True, nullable=False)
    webhook_secret = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(30), nullable=False, default='disconnected')
    phone_number = db.Column(db.String(30))
    webhook_configured = db.Column(db.Boolean, nullable=False, default=False)
    last_webhook_at = db.Column(UTCDateTime())
    __table_args__ = (UniqueConstraint('workspace_id'),)

    def to_dict(self):
        result = super().to_dict()
        result.pop('webhook_secret', None)
        return result


class WhatsAppConversation(TenantBase):
    __tablename__ = 'whatsapp_conversations'
    contact_id = db.Column(db.String(36), db.ForeignKey('contacts.id'), index=True)
    assigned_to_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    phone = db.Column(db.String(30), nullable=False)
    contact_name = db.Column(db.String(180))
    status = db.Column(db.String(20), nullable=False, default='open')
    unread_count = db.Column(db.Integer, nullable=False, default=0)
    last_message_at = db.Column(UTCDateTime())
    last_message_preview = db.Column(db.String(255))
    __table_args__ = (UniqueConstraint('workspace_id', 'phone'),)


class WhatsAppMessage(TenantBase):
    __tablename__ = 'whatsapp_messages'
    conversation_id = db.Column(db.String(36), db.ForeignKey('whatsapp_conversations.id'), nullable=False, index=True)
    provider_id = db.Column(db.String(180))
    direction = db.Column(db.String(10), nullable=False)
    content = db.Column(db.Text, nullable=False, default='')
    kind = db.Column(db.String(20), nullable=False, default='text')
    status = db.Column(db.String(20), nullable=False, default='received')
    sent_via = db.Column(db.String(20), nullable=False, default='whatsapp')
    sent_by_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    occurred_at = db.Column(UTCDateTime(), nullable=False, default=now)
    raw_message = db.Column(db.JSON)
    mimetype = db.Column(db.String(150))
    filename = db.Column(db.String(255))
    idempotency_key = db.Column(db.String(100))
    error = db.Column(db.String(500))
    __table_args__ = (UniqueConstraint('workspace_id', 'provider_id'), UniqueConstraint('workspace_id', 'idempotency_key'))

    def to_dict(self):
        result = super().to_dict()
        result.pop('raw_message', None)
        if self.kind != 'text':
            result['media_path'] = f'/whatsapp/messages/{self.id}/media'
        return result


class WhatsAppMedia(TenantBase):
    __tablename__ = 'whatsapp_media'
    message_id = db.Column(db.String(36), db.ForeignKey('whatsapp_messages.id'), unique=True, nullable=False)
    content = db.Column(db.LargeBinary, nullable=False)
    mimetype = db.Column(db.String(150), nullable=False)
    filename = db.Column(db.String(255), nullable=False)


class LeadForm(TenantBase):
    fields = db.Column(db.JSON, nullable=False, default=list)
    brand_name = db.Column(db.String(120), nullable=False, default='')
    accent_color = db.Column(db.String(7), nullable=False, default='#7542c6')
    __tablename__ = 'lead_forms'
    name = db.Column(db.String(150), nullable=False)
    headline = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False, default='')
    success_message = db.Column(db.String(500), nullable=False, default='Recebemos sua solicitação. Nossa equipe entrará em contato.')
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


class InstagramConnection(TenantBase):
    __tablename__ = 'instagram_connections'
    instagram_id = db.Column(db.String(80), nullable=False, unique=True)
    username = db.Column(db.String(150), nullable=False)
    encrypted_token = db.Column(db.Text, nullable=False)
    expires_at = db.Column(UTCDateTime())
    active = db.Column(db.Boolean, nullable=False, default=True)
    name = db.Column(db.String(150))
    profile_picture_url = db.Column(db.Text)
    profile_synced_at = db.Column(UTCDateTime())
    __table_args__ = (UniqueConstraint('workspace_id'),)

    def to_dict(self):
        return {key: value for key, value in super().to_dict().items() if key != 'encrypted_token'}


class InstagramOAuthState(TenantBase):
    __tablename__ = 'instagram_oauth_states'
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    state_hash = db.Column(db.String(64), nullable=False, unique=True)
    expires_at = db.Column(UTCDateTime(), nullable=False)
    consumed = db.Column(db.Boolean, nullable=False, default=False)


class InstagramEvent(TenantBase):
    __tablename__ = 'instagram_events'
    connection_id = db.Column(db.String(36), db.ForeignKey('instagram_connections.id'), nullable=False)
    event_key = db.Column(db.String(64), nullable=False, unique=True)
    kind = db.Column(db.String(40), nullable=False)
    payload = db.Column(db.JSON, nullable=False)


class InstagramComment(TenantBase):
    """A comment received on one of the connected account's posts; the target of automated replies."""
    __tablename__ = 'instagram_comments'
    connection_id = db.Column(db.String(36), db.ForeignKey('instagram_connections.id'), nullable=False)
    comment_id = db.Column(db.String(80), nullable=False, unique=True)
    media_id = db.Column(db.String(80))
    from_id = db.Column(db.String(80), nullable=False, index=True)
    username = db.Column(db.String(150))
    text = db.Column(db.Text, nullable=False, default='')
    contact_id = db.Column(db.String(36), db.ForeignKey('contacts.id'), index=True)
    replied_at = db.Column(UTCDateTime())
    private_replied_at = db.Column(UTCDateTime())


class MessageTemplate(TenantBase):
    __tablename__ = 'message_templates'
    name = db.Column(db.String(150), nullable=False)
    channel = db.Column(db.String(20), nullable=False)
    subject = db.Column(db.String(180), nullable=False, default='')
    content = db.Column(db.Text, nullable=False)


class InboxThread(TenantBase):
    __tablename__ = 'inbox_threads'
    channel = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(254), nullable=False)
    contact_id = db.Column(db.String(36), db.ForeignKey('contacts.id'), index=True)
    subject = db.Column(db.String(180), nullable=False, default='')
    __table_args__ = (UniqueConstraint('workspace_id', 'channel', 'address'),)


class InboxMessage(TenantBase):
    __tablename__ = 'inbox_messages'
    thread_id = db.Column(db.String(36), db.ForeignKey('inbox_threads.id'), nullable=False, index=True)
    direction = db.Column(db.String(10), nullable=False)
    content = db.Column(db.Text, nullable=False)
    subject = db.Column(db.String(180), nullable=False, default='')
    status = db.Column(db.String(20), nullable=False, default='queued')
    idempotency_key = db.Column(db.String(180), nullable=False)
    provider_id = db.Column(db.String(180))
    sent_by_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    scheduled_at = db.Column(UTCDateTime(), nullable=False, default=now, index=True)
    error = db.Column(db.String(500))
    __table_args__ = (UniqueConstraint('workspace_id', 'idempotency_key'),)


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


class CommunicationSuppression(TenantBase):
    __tablename__ = 'communication_suppressions'
    contact_id = db.Column(db.String(36), db.ForeignKey('contacts.id'), nullable=False, index=True)
    channel = db.Column(db.String(20), nullable=False)
    reason = db.Column(db.String(100), nullable=False, default='Solicitação do contato')
    __table_args__ = (UniqueConstraint('workspace_id', 'contact_id', 'channel'),)


class BookingCalendar(TenantBase):
    __tablename__ = 'booking_calendars'
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.String(2000), nullable=False, default='')
    assignee_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    duration_minutes = db.Column(db.Integer, nullable=False, default=30)
    buffer_minutes = db.Column(db.Integer, nullable=False, default=0)
    lead_minutes = db.Column(db.Integer, nullable=False, default=120)
    horizon_days = db.Column(db.Integer, nullable=False, default=60)
    availability = db.Column(db.JSON, nullable=False, default=lambda: {str(i): [{'start': '09:00', 'end': '18:00'}] for i in range(5)})
    active = db.Column(db.Boolean, nullable=False, default=False)


class Booking(TenantBase):
    __tablename__ = 'bookings'
    calendar_id = db.Column(db.String(36), db.ForeignKey('booking_calendars.id'), nullable=False, index=True)
    contact_id = db.Column(db.String(36), db.ForeignKey('contacts.id'), nullable=False)
    assignee_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    activity_id = db.Column(db.String(36), db.ForeignKey('activities.id'), nullable=False)
    starts_at = db.Column(UTCDateTime(), nullable=False, index=True)
    ends_at = db.Column(UTCDateTime(), nullable=False)
    buffer_minutes = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default='confirmed')
    submission_key = db.Column(db.String(36), nullable=False)
    consent_text = db.Column(db.String(255), nullable=False)
    __table_args__ = (UniqueConstraint('calendar_id', 'submission_key'), CheckConstraint('ends_at > starts_at'))


class SavedContactView(TenantBase):
    __tablename__ = 'saved_contact_views'
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    filters = db.Column(db.JSON, nullable=False)
    __table_args__ = (UniqueConstraint('workspace_id', 'user_id', 'name'),)


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
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending | approved | changes_requested | cancelled
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
