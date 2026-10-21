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
    __table_args__ = (UniqueConstraint('workspace_id'),)

    def to_dict(self):
        return {key: value for key, value in super().to_dict().items() if key != 'encrypted_token'}


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
