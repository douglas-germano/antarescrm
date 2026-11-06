"""Track browser requests for the local Atlas OAuth process."""

import sqlalchemy as sa
from alembic import op

revision = '20261105_atlas_ui'
down_revision = '20261105_atlas'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'atlas_connections',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('state', sa.String(20), nullable=False),
        sa.Column('connected', sa.Boolean(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.Column('seen_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('workspace_id'),
    )
    op.create_index('ix_atlas_connections_workspace_id', 'atlas_connections', ['workspace_id'])


def downgrade():
    op.drop_table('atlas_connections')
