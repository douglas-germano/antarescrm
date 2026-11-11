"""Keep archived campaigns and their delivery history."""

import sqlalchemy as sa
from alembic import op

revision = '20261106_campaign_archive'
down_revision = '20261106_atlas_automations'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('email_campaigns', sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('email_campaigns', 'archived')
