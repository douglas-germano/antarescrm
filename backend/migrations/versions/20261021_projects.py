"""Client projects: configurable stages, files with versions, approvals and a timeline."""
from alembic import op
import sqlalchemy as sa

revision = '20261021_projects'
down_revision = '20261021_instagram_profile'
branch_labels = depends_on = None


def base():
    return [sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False, index=True)]


def upgrade():
    op.create_table('project_stages', *base(), sa.Column('name', sa.String(80), nullable=False), sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('color', sa.String(7), nullable=False), sa.Column('is_final', sa.Boolean(), nullable=False),
        sa.UniqueConstraint('workspace_id', 'name', name='uq_project_stage_name'))
    op.create_table('projects', *base(),
        sa.Column('opportunity_id', sa.String(36), sa.ForeignKey('opportunities.id'), index=True),
        sa.Column('contact_id', sa.String(36), sa.ForeignKey('contacts.id'), index=True),
        sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id'), index=True),
        sa.Column('owner_id', sa.String(36), sa.ForeignKey('users.id')),
        sa.Column('stage_id', sa.String(36), sa.ForeignKey('project_stages.id'), nullable=False),
        sa.Column('title', sa.String(180), nullable=False), sa.Column('description', sa.Text()),
        sa.Column('amount', sa.Numeric(14, 2), nullable=False), sa.Column('status', sa.String(20), nullable=False),
        sa.Column('start_date', sa.Date()), sa.Column('due_date', sa.Date()), sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('workspace_id', 'opportunity_id', name='uq_project_opportunity'))
    op.create_table('project_files', *base(),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False, index=True),
        sa.Column('group_id', sa.String(36), nullable=False, index=True), sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False), sa.Column('title', sa.String(180), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False), sa.Column('mimetype', sa.String(150), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False), sa.Column('storage_key', sa.String(300), nullable=False),
        sa.Column('note', sa.Text()), sa.Column('uploaded_by', sa.String(36), sa.ForeignKey('users.id')),
        sa.Column('archived', sa.Boolean(), nullable=False))
    op.create_table('project_approvals', *base(),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False, index=True),
        sa.Column('file_id', sa.String(36), sa.ForeignKey('project_files.id')),
        sa.Column('title', sa.String(180), nullable=False), sa.Column('message', sa.Text()),
        sa.Column('status', sa.String(20), nullable=False), sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('token_hash', sa.String(64), unique=True), sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.Column('requested_by', sa.String(36), sa.ForeignKey('users.id')),
        sa.Column('decided_at', sa.DateTime(timezone=True)), sa.Column('decided_by', sa.String(150)),
        sa.Column('decided_ip', sa.String(64)), sa.Column('decision_comment', sa.Text()))
    op.create_table('project_events', *base(),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False, index=True),
        sa.Column('kind', sa.String(30), nullable=False), sa.Column('text', sa.String(500), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id')))


def downgrade():
    for name in ('project_events', 'project_approvals', 'project_files', 'projects', 'project_stages'):
        op.drop_table(name)
