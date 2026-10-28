"""Durable channel history imports; no import starts during migration."""
from alembic import op
import sqlalchemy as sa

revision = '20261028_history_sync'
down_revision = '20261022_message_notifications'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('history_syncs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('connection_id', sa.String(36), nullable=False),
        sa.Column('identity', sa.String(100), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('phase', sa.String(30), nullable=False),
        sa.Column('cursor', sa.JSON(), nullable=False),
        *[sa.Column(name, sa.Integer(), nullable=False)
          for name in ('scanned', 'imported', 'duplicates', 'skipped', 'unresolved', 'total')],
        sa.Column('error', sa.String(500)),
        sa.UniqueConstraint('workspace_id', 'channel'))
    op.create_index('ix_history_syncs_workspace_id', 'history_syncs', ['workspace_id'])


def downgrade():
    op.drop_table('history_syncs')
