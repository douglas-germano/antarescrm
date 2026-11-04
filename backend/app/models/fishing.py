"""Human-reviewed prospecting. No provider credentials are stored in these tables."""

from ..extensions import db
from .base import TenantBase, UTCDateTime


class FishingSettings(TenantBase):
    __tablename__ = 'fishing_settings'
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    brand_name = db.Column(db.String(150), nullable=False, default='')
    brand_profile = db.Column(db.Text, nullable=False, default='')
    tone = db.Column(db.String(300), nullable=False, default='')
    examples = db.Column(db.Text, nullable=False, default='')
    allowed_topics = db.Column(db.Text, nullable=False, default='')
    forbidden_words = db.Column(db.JSON, nullable=False, default=list)
    blocked_authors = db.Column(db.JSON, nullable=False, default=list)
    own_username = db.Column(db.String(30), nullable=False, default='')
    objective = db.Column(db.String(30), nullable=False, default='visitas')
    score_threshold = db.Column(db.Integer, nullable=False, default=60)
    daily_limit = db.Column(db.Integer, nullable=False, default=40)
    daily_ai_limit = db.Column(db.Integer, nullable=False, default=100)
    __table_args__ = (db.UniqueConstraint('workspace_id'),)


class FishingPost(TenantBase):
    __tablename__ = 'fishing_posts'
    url = db.Column(db.String(300), nullable=False)
    media_id = db.Column(db.String(100), nullable=False)
    author = db.Column(db.String(30), nullable=False, default='')
    caption = db.Column(db.Text, nullable=False)
    image_data = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default='novo')
    score = db.Column(db.Integer)
    reason = db.Column(db.String(300))
    summary = db.Column(db.String(600))
    error = db.Column(db.String(300))
    queued_at = db.Column(UTCDateTime())
    processing_at = db.Column(UTCDateTime())
    opened_at = db.Column(UTCDateTime())
    published_at = db.Column(UTCDateTime())
    decided_at = db.Column(UTCDateTime())
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    selected_draft_id = db.Column(db.String(36))
    published_text = db.Column(db.String(220))
    edited = db.Column(db.Boolean, nullable=False, default=False)
    __table_args__ = (
        db.UniqueConstraint('workspace_id', 'media_id'),
        db.Index('ix_fishing_posts_workspace_status', 'workspace_id', 'status'),
    )

    def to_dict(self):
        result = super().to_dict()
        result.pop('image_data', None)
        result['has_image'] = bool(self.image_data)
        return result


class FishingDraft(TenantBase):
    __tablename__ = 'fishing_drafts'
    post_id = db.Column(db.String(36), db.ForeignKey('fishing_posts.id'), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)
    text = db.Column(db.String(220), nullable=False)
    generation = db.Column(db.Integer, nullable=False)


class FishingUsage(TenantBase):
    __tablename__ = 'fishing_usage'
    post_id = db.Column(db.String(36), db.ForeignKey('fishing_posts.id'), nullable=False)
    model = db.Column(db.String(150), nullable=False)
    phase = db.Column(db.String(20), nullable=False)
    tokens = db.Column(db.Integer, nullable=False, default=0)
    cost_usd = db.Column(db.Numeric(16, 8))
