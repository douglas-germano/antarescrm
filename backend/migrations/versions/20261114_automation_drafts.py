"""Unpublished drafts of automation rules."""

import sqlalchemy as sa
from alembic import op

revision = '20261114_automation_drafts'
down_revision = '20261114_automation_versions'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('automation_rules') as batch:
        batch.add_column(sa.Column('draft', sa.JSON()))
        batch.add_column(sa.Column('draft_author_id', sa.String(36)))
        batch.add_column(sa.Column('draft_saved_at', sa.DateTime(timezone=True)))
        batch.create_foreign_key('fk_automation_rules_draft_author', 'users', ['draft_author_id'], ['id'])


def downgrade():
    with op.batch_alter_table('automation_rules') as batch:
        batch.drop_constraint('fk_automation_rules_draft_author', type_='foreignkey')
        batch.drop_column('draft_saved_at')
        batch.drop_column('draft_author_id')
        batch.drop_column('draft')
