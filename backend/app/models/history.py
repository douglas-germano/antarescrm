"""One durable, resumable history import per account and channel."""

from sqlalchemy import UniqueConstraint

from ..extensions import db
from .base import TenantBase


class HistorySync(TenantBase):
    __tablename__ = 'history_syncs'
    channel = db.Column(db.String(20), nullable=False)
    connection_id = db.Column(db.String(36), nullable=False)
    identity = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='queued')
    phase = db.Column(db.String(30), nullable=False)
    cursor = db.Column(db.JSON, nullable=False, default=dict)
    scanned = db.Column(db.Integer, nullable=False, default=0)
    imported = db.Column(db.Integer, nullable=False, default=0)
    duplicates = db.Column(db.Integer, nullable=False, default=0)
    skipped = db.Column(db.Integer, nullable=False, default=0)
    unresolved = db.Column(db.Integer, nullable=False, default=0)
    total = db.Column(db.Integer, nullable=False, default=0)
    error = db.Column(db.String(500))
    __table_args__ = (UniqueConstraint('workspace_id', 'channel'),)

    def public(self):
        result = {
            key: value for key, value in self.to_dict().items() if key not in ('cursor', 'identity', 'connection_id')
        }
        result['mapped_records'] = (self.cursor or {}).get('mapped_records', 0)
        return result
