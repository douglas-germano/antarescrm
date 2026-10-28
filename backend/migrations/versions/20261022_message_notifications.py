"""New inbound message notifications and per-user read cursors. No history backfill."""
from alembic import op
import sqlalchemy as sa

revision = '20261022_message_notifications'
down_revision = '20261022_campaign_channels'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('message_notifications',
        sa.Column('source', sa.String(16), nullable=False),
        sa.Column('thread_id', sa.String(36), nullable=False),
        sa.Column('message_id', sa.String(36), nullable=False),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('sender_name', sa.String(180), nullable=False),
        sa.Column('preview', sa.String(255), nullable=False),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False),
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('workspace_id', 'source', 'message_id'))
    op.create_index('ix_message_notifications_workspace_id', 'message_notifications', ['workspace_id'])
    op.create_index('ix_message_notifications_thread', 'message_notifications', ['workspace_id', 'source', 'thread_id', 'created_at'])
    op.create_table('notification_read_states',
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('source', sa.String(16), nullable=False),
        sa.Column('thread_id', sa.String(36), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('read_id', sa.String(36), nullable=False),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False),
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('workspace_id', 'user_id', 'source', 'thread_id'))
    op.create_index('ix_notification_read_states_workspace_id', 'notification_read_states', ['workspace_id'])


def downgrade():
    op.drop_table('notification_read_states')
    op.drop_table('message_notifications')
