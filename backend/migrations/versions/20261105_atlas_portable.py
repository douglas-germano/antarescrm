"""Persist the portable Atlas OAuth transaction in PostgreSQL."""

import sqlalchemy as sa
from alembic import op

revision = '20261105_atlas_portable'
down_revision = '20261105_atlas_ui'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('atlas_connections', sa.Column('oauth_state', sa.String(64)))
    op.add_column('atlas_connections', sa.Column('oauth_attempt', sa.Text()))
    op.add_column('atlas_connections', sa.Column('oauth_host', sa.String(45)))
    op.create_index('ix_atlas_connections_oauth_state', 'atlas_connections', ['oauth_state'], unique=True)


def downgrade():
    op.drop_index('ix_atlas_connections_oauth_state', table_name='atlas_connections')
    for name in ('oauth_host', 'oauth_attempt', 'oauth_state'):
        op.drop_column('atlas_connections', name)
