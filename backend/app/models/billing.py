from ..extensions import db
from .base import Base, TenantBase, UTCDateTime


class Subscription(TenantBase):
    """Billing state of a top-level workspace. Workspaces without a row are not billed (internal/legacy)."""

    __tablename__ = 'subscriptions'
    status = db.Column(db.String(20), nullable=False, default='trialing')  # trialing | active | past_due | canceled
    trial_ends_at = db.Column(UTCDateTime())
    past_due_since = db.Column(UTCDateTime())
    last_paid_at = db.Column(UTCDateTime())
    next_due_date = db.Column(db.Date())
    asaas_customer_id = db.Column(db.String(64))
    asaas_subscription_id = db.Column(db.String(64), unique=True)
    invoice_url = db.Column(db.String(500))
    __table_args__ = (db.UniqueConstraint('workspace_id'),)


class BillingEvent(Base):
    """One row per Asaas webhook event id, so retries and duplicates are applied only once."""

    __tablename__ = 'billing_events'
    event_id = db.Column(db.String(80), nullable=False, unique=True)
    event_type = db.Column(db.String(60), nullable=False)
    workspace_id = db.Column(db.String(36), db.ForeignKey('workspaces.id'), index=True)
