from sqlalchemy import UniqueConstraint

from ..extensions import db
from .base import TenantBase, UTCDateTime, now


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
    __table_args__ = (
        UniqueConstraint('workspace_id', 'provider_id'),
        UniqueConstraint('workspace_id', 'idempotency_key'),
    )

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
