from sqlalchemy import Index, UniqueConstraint

from ..extensions import db
from .base import TenantBase, UTCDateTime


class MessageNotification(TenantBase):
    __tablename__ = 'message_notifications'
    source = db.Column(db.String(16), nullable=False)
    thread_id = db.Column(db.String(36), nullable=False)
    message_id = db.Column(db.String(36), nullable=False)
    channel = db.Column(db.String(20), nullable=False)
    sender_name = db.Column(db.String(180), nullable=False)
    preview = db.Column(db.String(255), nullable=False)
    __table_args__ = (
        UniqueConstraint('workspace_id', 'source', 'message_id'),
        Index('ix_message_notifications_thread', 'workspace_id', 'source', 'thread_id', 'created_at'),
    )


class NotificationReadState(TenantBase):
    __tablename__ = 'notification_read_states'
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    source = db.Column(db.String(16), nullable=False)
    thread_id = db.Column(db.String(36), nullable=False)
    read_at = db.Column(UTCDateTime(), nullable=False)
    read_id = db.Column(db.String(36), nullable=False)
    __table_args__ = (UniqueConstraint('workspace_id', 'user_id', 'source', 'thread_id'),)
