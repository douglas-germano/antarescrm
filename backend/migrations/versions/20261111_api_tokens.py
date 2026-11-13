"""API tokens for AI clients (MCP), scoped to one account and a set of permissions."""

import sqlalchemy as sa
from alembic import op

revision = '20261111_api_tokens'
down_revision = '20261111_instagram_publishing'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'api_tokens',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('prefix', sa.String(16), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('scopes', sa.JSON(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.Column('last_used_at', sa.DateTime(timezone=True)),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
    )


def downgrade():
    op.drop_table('api_tokens')
