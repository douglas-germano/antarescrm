"""Persist Atlas playbooks, conversation memory and job outcomes."""

import sqlalchemy as sa
from alembic import op

revision = '20261106_atlas_workflow'
down_revision = '20261105_atlas_db_key'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('atlas_connections', sa.Column('playbook', sa.JSON()))
    op.add_column('atlas_targets', sa.Column('memory', sa.Text()))
    op.add_column('atlas_jobs', sa.Column('insight', sa.JSON()))


def downgrade():
    op.drop_column('atlas_jobs', 'insight')
    op.drop_column('atlas_targets', 'memory')
    op.drop_column('atlas_connections', 'playbook')
