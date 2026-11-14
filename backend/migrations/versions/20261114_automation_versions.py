"""Version history of automation rules."""

import sqlalchemy as sa
from alembic import op

revision = '20261114_automation_versions'
down_revision = '20261113_billing'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'automation_rule_versions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False, index=True),
        sa.Column('rule_id', sa.String(36), sa.ForeignKey('automation_rules.id'), nullable=False, index=True),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('author_id', sa.String(36), sa.ForeignKey('users.id')),
        sa.Column('note', sa.String(200)),
        sa.UniqueConstraint('rule_id', 'number'),
    )


def downgrade():
    op.drop_table('automation_rule_versions')
