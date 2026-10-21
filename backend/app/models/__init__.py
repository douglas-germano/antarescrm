"""Modelos SQLAlchemy organizados por domínio; reexportados aqui para `from app.models import X`."""

from .automation import AutomationJob, AutomationRule, AutomationRun, FormSubmission, LeadForm, WorkerHeartbeat
from .base import Base, TenantBase, UTCDateTime, now, uid
from .booking import Booking, BookingCalendar
from .communications import CommunicationSuppression, InboxMessage, InboxThread, MessageTemplate
from .crm import Activity, Company, Contact, Opportunity, Pipeline, PipelineStage, SavedContactView, StageHistory, Task
from .domains import CustomDomain
from .funnels import Funnel, FunnelEvent, FunnelStep
from .instagram import InstagramComment, InstagramConnection, InstagramEvent, InstagramOAuthState
from .projects import Project, ProjectApproval, ProjectEvent, ProjectFile, ProjectStage
from .tenancy import AuditLog, User, Workspace, WorkspaceAccess
from .whatsapp import WhatsAppConnection, WhatsAppConversation, WhatsAppMedia, WhatsAppMessage

__all__ = [
    'CustomDomain',
    'Funnel',
    'FunnelEvent',
    'FunnelStep',
    'Base',
    'TenantBase',
    'UTCDateTime',
    'now',
    'uid',
    'Workspace',
    'User',
    'WorkspaceAccess',
    'AuditLog',
    'Company',
    'Contact',
    'Pipeline',
    'PipelineStage',
    'Opportunity',
    'StageHistory',
    'Activity',
    'Task',
    'SavedContactView',
    'WhatsAppConnection',
    'WhatsAppConversation',
    'WhatsAppMessage',
    'WhatsAppMedia',
    'LeadForm',
    'FormSubmission',
    'AutomationRule',
    'AutomationRun',
    'AutomationJob',
    'WorkerHeartbeat',
    'InstagramConnection',
    'InstagramOAuthState',
    'InstagramEvent',
    'InstagramComment',
    'MessageTemplate',
    'InboxThread',
    'InboxMessage',
    'CommunicationSuppression',
    'BookingCalendar',
    'Booking',
    'ProjectStage',
    'Project',
    'ProjectFile',
    'ProjectApproval',
    'ProjectEvent',
]
