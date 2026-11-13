"""Modelos SQLAlchemy organizados por domínio; reexportados aqui para `from app.models import X`."""

from .api_tokens import TOKEN_SCOPES, ApiToken
from .atlas import AtlasConnection, AtlasCredential, AtlasJob, AtlasTarget
from .automation import AutomationJob, AutomationRule, AutomationRun, FormSubmission, LeadForm, WorkerHeartbeat
from .base import Base, TenantBase, UTCDateTime, now, uid
from .booking import Booking, BookingCalendar
from .brevo import BrevoConnection, BrevoEvent, CampaignRecipient, EmailCampaign, UserAccessToken
from .communications import CommunicationSuppression, InboxMessage, InboxThread, MessageTemplate
from .crm import Activity, Company, Contact, Opportunity, Pipeline, PipelineStage, SavedContactView, StageHistory, Task
from .domains import CustomDomain
from .fishing import FishingDraft, FishingPost, FishingSettings, FishingUsage
from .funnels import Funnel, FunnelEvent, FunnelStep
from .history import HistorySync
from .instagram import (
    InstagramComment,
    InstagramConnection,
    InstagramEvent,
    InstagramInsightSnapshot,
    InstagramMedia,
    InstagramOAuthState,
    InstagramPost,
)
from .notifications import MessageNotification, NotificationReadState
from .projects import Project, ProjectApproval, ProjectEvent, ProjectFile, ProjectStage
from .tenancy import AuditLog, User, Workspace, WorkspaceAccess
from .whatsapp import WhatsAppConnection, WhatsAppConversation, WhatsAppMedia, WhatsAppMessage

__all__ = [
    'AtlasConnection',
    'AtlasCredential',
    'AtlasJob',
    'AtlasTarget',
    'FishingDraft',
    'FishingPost',
    'FishingSettings',
    'FishingUsage',
    'HistorySync',
    'MessageNotification',
    'NotificationReadState',
    'BrevoConnection',
    'BrevoEvent',
    'CampaignRecipient',
    'EmailCampaign',
    'UserAccessToken',
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
    'ApiToken',
    'TOKEN_SCOPES',
    'InstagramConnection',
    'InstagramInsightSnapshot',
    'InstagramMedia',
    'InstagramPost',
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
