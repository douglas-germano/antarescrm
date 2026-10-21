"""Agency accounts and explicit team access.

Revision ID: 20261020_agency
Revises: 7e314cb26226
"""
from alembic import op
import sqlalchemy as sa

revision = '20261020_agency'
down_revision = '7e314cb26226'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('workspaces') as batch:
        batch.add_column(sa.Column('parent_workspace_id', sa.String(36), nullable=True))
        batch.add_column(sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.create_foreign_key('fk_workspaces_parent', 'workspaces', ['parent_workspace_id'], ['id'])
        batch.create_index('ix_workspaces_parent_workspace_id', ['parent_workspace_id'])
    op.create_table('workspace_access',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.UniqueConstraint('workspace_id', 'user_id'))
    op.create_index('ix_workspace_access_workspace_id', 'workspace_access', ['workspace_id'])
    op.create_index('ix_workspace_access_user_id', 'workspace_access', ['user_id'])


def downgrade():
    op.drop_table('workspace_access')
    with op.batch_alter_table('workspaces') as batch:
        batch.drop_index('ix_workspaces_parent_workspace_id')
        batch.drop_constraint('fk_workspaces_parent', type_='foreignkey')
        batch.drop_column('parent_workspace_id')
        batch.drop_column('active')
