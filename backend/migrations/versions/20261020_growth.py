"""Lead capture and immediate task automations.
Revision ID: 20261020_growth
Revises: 20261020_agency
"""
from alembic import op
import sqlalchemy as sa
revision = '20261020_growth'
down_revision = '20261020_agency'
branch_labels = None
depends_on = None


def base():
    return [sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False)]


def upgrade():
    op.create_table('lead_forms', *base(),
        sa.Column('name', sa.String(150), nullable=False), sa.Column('headline', sa.String(180), nullable=False),
        sa.Column('description', sa.Text(), nullable=False), sa.Column('success_message', sa.String(500), nullable=False),
        sa.Column('stage_id', sa.String(36), sa.ForeignKey('pipeline_stages.id'), nullable=False),
        sa.Column('source', sa.String(100), nullable=False), sa.Column('active', sa.Boolean(), nullable=False))
    op.create_table('form_submissions', *base(),
        sa.Column('form_id', sa.String(36), sa.ForeignKey('lead_forms.id'), nullable=False),
        sa.Column('submission_key', sa.String(36), nullable=False),
        sa.Column('contact_id', sa.String(36), sa.ForeignKey('contacts.id'), nullable=False),
        sa.Column('opportunity_id', sa.String(36), sa.ForeignKey('opportunities.id'), nullable=False),
        sa.Column('consent_text', sa.String(255), nullable=False), sa.UniqueConstraint('form_id', 'submission_key'))
    op.create_index('ix_form_submissions_form_id', 'form_submissions', ['form_id'])
    op.create_table('automation_rules', *base(),
        sa.Column('name', sa.String(150), nullable=False), sa.Column('event', sa.String(40), nullable=False),
        sa.Column('source', sa.String(100)), sa.Column('task_title', sa.String(180), nullable=False),
        sa.Column('due_days', sa.Integer(), nullable=False),
        sa.Column('assignee_id', sa.String(36), sa.ForeignKey('users.id')),
        sa.Column('active', sa.Boolean(), nullable=False))
    op.create_table('automation_runs', *base(),
        sa.Column('rule_id', sa.String(36), sa.ForeignKey('automation_rules.id'), nullable=False),
        sa.Column('event_key', sa.String(100), nullable=False),
        sa.Column('contact_id', sa.String(36), sa.ForeignKey('contacts.id'), nullable=False),
        sa.Column('task_id', sa.String(36), sa.ForeignKey('tasks.id', ondelete='SET NULL')),
        sa.Column('status', sa.String(20), nullable=False), sa.Column('detail', sa.String(500), nullable=False),
        sa.UniqueConstraint('rule_id', 'event_key'))
    for table in ('lead_forms', 'form_submissions', 'automation_rules', 'automation_runs'):
        op.create_index('ix_' + table + '_workspace_id', table, ['workspace_id'])


def downgrade():
    for table in ('automation_runs', 'automation_rules', 'form_submissions', 'lead_forms'):
        op.drop_table(table)
