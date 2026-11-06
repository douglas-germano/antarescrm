"""Persist the originating automation for Atlas jobs."""

import sqlalchemy as sa
from alembic import op

revision = '20261106_atlas_automations'
down_revision = '20261106_atlas_workflow'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('atlas_jobs', sa.Column('automation_context', sa.JSON()))


def downgrade():
    op.drop_column('atlas_jobs', 'automation_context')
