"""Account-scoped Instagram credentials, OAuth nonces and durable inbound events."""
from alembic import op
import sqlalchemy as sa

revision = '20261021_instagram'
down_revision = '20261021_stage_probability'
branch_labels = depends_on = None


def upgrade():
    base = lambda: [sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False, index=True)]
    op.create_table('instagram_connections', *base(),
        sa.Column('instagram_id', sa.String(80), nullable=False, unique=True),
        sa.Column('username', sa.String(150), nullable=False), sa.Column('encrypted_token', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True)), sa.Column('active', sa.Boolean(), nullable=False),
        sa.UniqueConstraint('workspace_id'))
    op.create_table('instagram_oauth_states', *base(),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('state_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False), sa.Column('consumed', sa.Boolean(), nullable=False))
    op.create_table('instagram_events', *base(),
        sa.Column('connection_id', sa.String(36), sa.ForeignKey('instagram_connections.id'), nullable=False),
        sa.Column('event_key', sa.String(64), nullable=False, unique=True), sa.Column('kind', sa.String(40), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False))


def downgrade():
    for name in ['instagram_events', 'instagram_oauth_states', 'instagram_connections']:
        op.drop_table(name)
