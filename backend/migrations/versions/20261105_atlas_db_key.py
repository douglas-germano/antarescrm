"""Store the Atlas OAuth encryption key per workspace."""

import sqlalchemy as sa
from alembic import op

revision = '20261105_atlas_db_key'
down_revision = '20261105_atlas_portable'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('atlas_connections', sa.Column('oauth_key', sa.String(44)))


def downgrade():
    op.drop_column('atlas_connections', 'oauth_key')
