"""Conditional multi-step workflows and durable scheduled jobs."""
from alembic import op
import sqlalchemy as sa
revision = '20261021_workflows'
down_revision = '20261021_communications'
branch_labels = depends_on = None


def upgrade():
    op.add_column('automation_rules', sa.Column('required_tag', sa.String(80)))
    op.add_column('automation_rules', sa.Column('actions', sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    if op.get_bind().dialect.name != 'sqlite': op.alter_column('automation_rules', 'actions', server_default=None)
    op.create_table('automation_jobs', sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False), sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False),
        sa.Column('run_id', sa.String(36), sa.ForeignKey('automation_runs.id'), nullable=False), sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('action', sa.JSON(), nullable=False), sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(20), nullable=False), sa.Column('result_id', sa.String(36)), sa.Column('detail', sa.String(500)),
        sa.UniqueConstraint('run_id', 'position'))
    for column in ('workspace_id', 'run_id', 'scheduled_at'): op.create_index('ix_automation_jobs_' + column, 'automation_jobs', [column])


def downgrade():
    op.drop_table('automation_jobs')
    op.drop_column('automation_rules', 'actions')
    op.drop_column('automation_rules', 'required_tag')
