from sqlalchemy import UniqueConstraint

from ..extensions import db
from .base import TenantBase


class Funnel(TenantBase):
    __tablename__ = 'funnels'
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False, default='')
    status = db.Column(db.String(20), nullable=False, default='draft')
    theme = db.Column(db.JSON, nullable=False, default=dict)


class FunnelStep(TenantBase):
    __tablename__ = 'funnel_steps'
    funnel_id = db.Column(db.String(36), db.ForeignKey('funnels.id'), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(60), nullable=False)
    kind = db.Column(db.String(20), nullable=False, default='landing')
    position = db.Column(db.Integer, nullable=False, default=0)
    blocks = db.Column(db.JSON, nullable=False, default=list)
    settings = db.Column(db.JSON, nullable=False, default=dict)
    __table_args__ = (UniqueConstraint('funnel_id', 'slug', name='uq_funnel_step_slug'),)


class FunnelEvent(TenantBase):
    __tablename__ = 'funnel_events'
    funnel_id = db.Column(db.String(36), db.ForeignKey('funnels.id'), nullable=False, index=True)
    step_id = db.Column(db.String(36), db.ForeignKey('funnel_steps.id'), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)
    visitor_id = db.Column(db.String(36), nullable=False)
