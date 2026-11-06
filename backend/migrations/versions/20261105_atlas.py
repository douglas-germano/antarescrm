"""Atlas pilot enrollments and delivery jobs."""

import sqlalchemy as sa
from alembic import op

revision = '20261105_atlas'
down_revision = '20261103_fishing'
branch_labels = None
depends_on = None


def base():
    return [
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade():
    op.create_table(
        'atlas_targets',
        *base(),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('conversation_id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('brief', sa.Text(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.UniqueConstraint('workspace_id', 'channel', 'conversation_id'),
    )
    op.create_table(
        'atlas_jobs',
        *base(),
        sa.Column('target_id', sa.String(36), sa.ForeignKey('atlas_targets.id'), nullable=False),
        sa.Column('trigger_id', sa.String(36), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('claimed_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('target_id', 'trigger_id'),
    )
    op.create_table(
        'atlas_credentials',
        *base(),
        sa.Column('ciphertext', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.UniqueConstraint('workspace_id'),
    )
    for table in ('atlas_targets', 'atlas_jobs', 'atlas_credentials'):
        op.create_index(f'ix_{table}_workspace_id', table, ['workspace_id'])
    op.create_index('ix_atlas_jobs_target_id', 'atlas_jobs', ['target_id'])


def downgrade():
    op.drop_table('atlas_credentials')
    op.drop_table('atlas_jobs')
    op.drop_table('atlas_targets')
