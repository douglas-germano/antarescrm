"""Private provider connections, access links and account-scoped email campaigns."""

from sqlalchemy import UniqueConstraint

from ..extensions import db
from .base import TenantBase, UTCDateTime


class BrevoConnection(TenantBase):
    __tablename__ = 'brevo_connections'
    encrypted_key = db.Column(db.Text, nullable=False)
    sender_email = db.Column(db.String(254), nullable=False)
    sender_name = db.Column(db.String(150), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    validated_at = db.Column(UTCDateTime(), nullable=False)
    folder_id = db.Column(db.Integer)
    webhook_secret = db.Column(db.String(100), nullable=False)
    webhook_id = db.Column(db.Integer)
    __table_args__ = (UniqueConstraint('workspace_id'),)

    def to_dict(self):
        return {
            key: getattr(self, key)
            for key in ('id', 'workspace_id', 'sender_email', 'sender_name', 'active', 'webhook_id')
        } | {'validated_at': self.validated_at.isoformat(), 'configured': bool(self.active and self.encrypted_key)}


class UserAccessToken(TenantBase):
    __tablename__ = 'user_access_tokens'
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    purpose = db.Column(db.String(20), nullable=False)
    token_version = db.Column(db.Integer, nullable=False)
    email = db.Column(db.String(254), nullable=False)
    expires_at = db.Column(UTCDateTime(), nullable=False)
    consumed_at = db.Column(UTCDateTime())
    delivery_status = db.Column(db.String(20), nullable=False, default='sending')


class EmailCampaign(TenantBase):
    # Retain the historical table name so existing Brevo campaigns keep their IDs.
    __tablename__ = 'email_campaigns'
    channel = db.Column(db.String(20), nullable=False, default='email')
    name = db.Column(db.String(150), nullable=False)
    subject = db.Column(db.String(180), nullable=False)
    content = db.Column(db.Text, nullable=False)
    audience = db.Column(db.JSON, nullable=False, default=dict)
    status = db.Column(db.String(20), nullable=False, default='draft')
    connection_id = db.Column(db.String(36), db.ForeignKey('brevo_connections.id'))
    connection_version = db.Column(db.Integer)
    whatsapp_connection_id = db.Column(db.String(36), db.ForeignKey('whatsapp_connections.id'))
    provider_id = db.Column(db.Integer)
    list_id = db.Column(db.Integer)
    process_id = db.Column(db.Integer)
    audience_hash = db.Column(db.String(64))
    recipient_count = db.Column(db.Integer, nullable=False, default=0)
    sent_at = db.Column(UTCDateTime())
    error = db.Column(db.String(300))


class CampaignRecipient(TenantBase):
    __tablename__ = 'campaign_recipients'
    campaign_id = db.Column(db.String(36), db.ForeignKey('email_campaigns.id'), nullable=False, index=True)
    contact_id = db.Column(db.String(36), db.ForeignKey('contacts.id'), nullable=False)
    email = db.Column(db.String(254))
    phone = db.Column(db.String(20))
    message_id = db.Column(db.String(36), db.ForeignKey('inbox_messages.id'), unique=True)
    status = db.Column(db.String(20), nullable=False, default='prepared')
    events = db.Column(db.JSON, nullable=False, default=dict)
    __table_args__ = (UniqueConstraint('campaign_id', 'email'), UniqueConstraint('campaign_id', 'phone'))


class BrevoEvent(TenantBase):
    __tablename__ = 'brevo_events'
    connection_id = db.Column(db.String(36), db.ForeignKey('brevo_connections.id'), nullable=False)
    event_key = db.Column(db.String(64), nullable=False, unique=True)
    campaign_id = db.Column(db.String(36), db.ForeignKey('email_campaigns.id'), nullable=False)
    kind = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(254), nullable=False)
