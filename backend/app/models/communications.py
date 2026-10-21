from sqlalchemy import UniqueConstraint

from ..extensions import db
from .base import TenantBase, UTCDateTime, now


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


class CommunicationSuppression(TenantBase):
    __tablename__ = 'communication_suppressions'
    contact_id = db.Column(db.String(36), db.ForeignKey('contacts.id'), nullable=False, index=True)
    channel = db.Column(db.String(20), nullable=False)
    reason = db.Column(db.String(100), nullable=False, default='Solicitação do contato')
    __table_args__ = (UniqueConstraint('workspace_id', 'contact_id', 'channel'),)
