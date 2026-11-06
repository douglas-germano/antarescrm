from sqlalchemy import UniqueConstraint

from ..extensions import db
from .base import TenantBase, UTCDateTime


class AtlasTarget(TenantBase):
    __tablename__ = 'atlas_targets'
    channel = db.Column(db.String(20), nullable=False)
    conversation_id = db.Column(db.String(36), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    brief = db.Column(db.Text, nullable=False)
    memory = db.Column(db.Text)
    active = db.Column(db.Boolean, nullable=False, default=True)
    __table_args__ = (UniqueConstraint('workspace_id', 'channel', 'conversation_id'),)


class AtlasJob(TenantBase):
    __tablename__ = 'atlas_jobs'
    target_id = db.Column(db.String(36), db.ForeignKey('atlas_targets.id'), nullable=False, index=True)
    trigger_id = db.Column(db.String(36), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='queued')
    claimed_at = db.Column(UTCDateTime())
    insight = db.Column(db.JSON)
    automation_context = db.Column(db.JSON)
    __table_args__ = (UniqueConstraint('target_id', 'trigger_id'),)


class AtlasCredential(TenantBase):
    __tablename__ = 'atlas_credentials'
    ciphertext = db.Column(db.Text, nullable=False)
    version = db.Column(db.Integer, nullable=False)
    __table_args__ = (UniqueConstraint('workspace_id'),)


class AtlasConnection(TenantBase):
    __tablename__ = 'atlas_connections'
    state = db.Column(db.String(20), nullable=False)
    connected = db.Column(db.Boolean, nullable=False, default=False)
    expires_at = db.Column(UTCDateTime())
    seen_at = db.Column(UTCDateTime())
    __table_args__ = (UniqueConstraint('workspace_id'),)
    oauth_state = db.Column(db.String(64), unique=True, index=True)
    oauth_attempt = db.Column(db.Text)
    oauth_host = db.Column(db.String(45))
    oauth_key = db.Column(db.String(44))
    playbook = db.Column(db.JSON)
