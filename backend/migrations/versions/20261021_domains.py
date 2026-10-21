"""Custom domains for public funnel, form and booking pages."""
import sqlalchemy as sa
from alembic import op

revision = '20261021_domains'
down_revision = '20261021_funnels'
branch_labels = depends_on = None


def upgrade():
    op.create_table('custom_domains',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False, index=True),
        sa.Column('hostname', sa.String(253), nullable=False, unique=True),
        sa.Column('funnel_id', sa.String(36), sa.ForeignKey('funnels.id'), index=True),
        sa.Column('verification_token', sa.String(64), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True)),
        sa.Column('routing_ok', sa.Boolean(), nullable=False),
        sa.Column('last_checked_at', sa.DateTime(timezone=True)),
        sa.Column('last_error', sa.String(300), nullable=False),
        sa.Column('tls_ref', sa.String(100)),
        sa.Column('tls_status', sa.String(20), nullable=False))


def downgrade():
    op.drop_table('custom_domains')
