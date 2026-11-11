from sqlalchemy import UniqueConstraint

from ..extensions import db
from .base import TenantBase, UTCDateTime


class InstagramConnection(TenantBase):
    __tablename__ = 'instagram_connections'
    instagram_id = db.Column(db.String(80), nullable=False, unique=True)
    username = db.Column(db.String(150), nullable=False)
    encrypted_token = db.Column(db.Text, nullable=False)
    expires_at = db.Column(UTCDateTime())
    active = db.Column(db.Boolean, nullable=False, default=True)
    name = db.Column(db.String(150))
    profile_picture_url = db.Column(db.Text)
    profile_synced_at = db.Column(UTCDateTime())
    # Permissions granted at authorization. None: authorized before publishing and metrics were requested.
    scopes = db.Column(db.Text)

    def to_dict(self):
        result = {key: value for key, value in super().to_dict().items() if key not in ('encrypted_token', 'scopes')}
        granted = set((self.scopes or '').split(','))
        result['can_publish'] = 'instagram_business_content_publish' in granted
        result['can_read_insights'] = 'instagram_business_manage_insights' in granted
        return result


class InstagramOAuthState(TenantBase):
    __tablename__ = 'instagram_oauth_states'
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    state_hash = db.Column(db.String(64), nullable=False, unique=True)
    expires_at = db.Column(UTCDateTime(), nullable=False)
    consumed = db.Column(db.Boolean, nullable=False, default=False)


class InstagramEvent(TenantBase):
    __tablename__ = 'instagram_events'
    connection_id = db.Column(db.String(36), db.ForeignKey('instagram_connections.id'), nullable=False)
    event_key = db.Column(db.String(64), nullable=False, unique=True)
    kind = db.Column(db.String(40), nullable=False)
    payload = db.Column(db.JSON, nullable=False)


class InstagramComment(TenantBase):
    """A comment received on one of the connected account's posts; the target of automated replies."""

    __tablename__ = 'instagram_comments'
    connection_id = db.Column(db.String(36), db.ForeignKey('instagram_connections.id'), nullable=False)
    comment_id = db.Column(db.String(80), nullable=False, unique=True)
    media_id = db.Column(db.String(80))
    from_id = db.Column(db.String(80), nullable=False, index=True)
    username = db.Column(db.String(150))
    text = db.Column(db.Text, nullable=False, default='')
    contact_id = db.Column(db.String(36), db.ForeignKey('contacts.id'), index=True)
    replied_at = db.Column(UTCDateTime())
    private_replied_at = db.Column(UTCDateTime())


class InstagramMedia(TenantBase):
    """A file uploaded for publication. Instagram downloads it from a public, unguessable link."""

    __tablename__ = 'instagram_media'
    filename = db.Column(db.String(255), nullable=False)
    kind = db.Column(db.String(10), nullable=False)  # image | video
    content_type = db.Column(db.String(80), nullable=False)
    size = db.Column(db.Integer, nullable=False)
    storage_key = db.Column(db.String(255), nullable=False)
    public_token = db.Column(db.String(64), nullable=False, unique=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey('users.id'))

    def to_dict(self):
        return {key: value for key, value in super().to_dict().items() if key not in ('storage_key', 'public_token')}


class InstagramPost(TenantBase):
    """A feed post, carousel or reel published (now or on a schedule) through one connected account."""

    __tablename__ = 'instagram_posts'
    connection_id = db.Column(db.String(36), db.ForeignKey('instagram_connections.id'), nullable=False, index=True)
    media_type = db.Column(db.String(20), nullable=False)  # IMAGE | CAROUSEL | REELS
    caption = db.Column(db.Text, nullable=False, default='')
    items = db.Column(db.JSON, nullable=False, default=list)  # [{kind, media_id?|url?}]
    # draft | scheduled | processing | publishing | published | failed | unknown
    status = db.Column(db.String(20), nullable=False, default='draft', index=True)
    scheduled_at = db.Column(UTCDateTime(), index=True)
    containers = db.Column(db.JSON, nullable=False, default=dict)  # {children: [...], parent: id}
    processing_since = db.Column(UTCDateTime())
    ig_media_id = db.Column(db.String(80))
    permalink = db.Column(db.Text)
    published_at = db.Column(UTCDateTime())
    error = db.Column(db.String(500))
    created_by_id = db.Column(db.String(36), db.ForeignKey('users.id'))

    def to_dict(self):
        return {key: value for key, value in super().to_dict().items() if key != 'containers'}


class InstagramInsightSnapshot(TenantBase):
    """Daily snapshot of an account's metrics: keeps history beyond the API's window and spares rate limits."""

    __tablename__ = 'instagram_insight_snapshots'
    connection_id = db.Column(db.String(36), db.ForeignKey('instagram_connections.id'), nullable=False)
    day = db.Column(db.Date, nullable=False)
    period = db.Column(db.Integer, nullable=False, default=30)
    data = db.Column(db.JSON, nullable=False, default=dict)
    __table_args__ = (UniqueConstraint('connection_id', 'day', 'period'),)
