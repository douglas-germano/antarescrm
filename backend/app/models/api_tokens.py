from ..extensions import db
from .base import TenantBase, UTCDateTime

# Permissions an API token can carry. Each MCP tool requires one of them.
TOKEN_SCOPES = {
    'messages:read': 'Ler conversas e mensagens',
    'messages:send': 'Enviar mensagens nas conversas',
    'instagram:read': 'Ler perfis, publicações, comentários e métricas do Instagram',
    'instagram:drafts': 'Criar rascunhos de publicações',
    'instagram:publish': 'Publicar e agendar posts',
    'instagram:comments': 'Responder comentários',
}


class ApiToken(TenantBase):
    """A credential for AI clients (MCP). Acts as its creator inside one account, limited to its scopes.
    Only the SHA-256 of the secret is stored; the secret is shown once at creation."""

    __tablename__ = 'api_tokens'
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    prefix = db.Column(db.String(16), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    scopes = db.Column(db.JSON, nullable=False, default=list)
    expires_at = db.Column(UTCDateTime())
    last_used_at = db.Column(UTCDateTime())
    revoked_at = db.Column(UTCDateTime())

    def to_dict(self):
        return {key: value for key, value in super().to_dict().items() if key != 'token_hash'}
