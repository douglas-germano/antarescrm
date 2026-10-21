from ..extensions import db
from .base import TenantBase, UTCDateTime


class CustomDomain(TenantBase):
    __tablename__ = 'custom_domains'
    hostname = db.Column(db.String(253), nullable=False, unique=True)
    funnel_id = db.Column(db.String(36), db.ForeignKey('funnels.id'), index=True)
    verification_token = db.Column(db.String(64), nullable=False)
    verified_at = db.Column(UTCDateTime())
    routing_ok = db.Column(db.Boolean, nullable=False, default=False)
    last_checked_at = db.Column(UTCDateTime())
    last_error = db.Column(db.String(300), nullable=False, default='')
    tls_ref = db.Column(db.String(100))
    tls_status = db.Column(db.String(20), nullable=False, default='none')
