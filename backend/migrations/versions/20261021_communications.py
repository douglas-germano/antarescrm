"""Unified inbox, templates and durable outbound messages."""
from alembic import op
import sqlalchemy as sa
revision = '20261021_communications'
down_revision = '20261021_crm_fields'
branch_labels = depends_on = None


def base():
    return [sa.Column('id', sa.String(36), primary_key=True), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False)]


def upgrade():
    op.create_table('message_templates', *base(), sa.Column('name', sa.String(150), nullable=False), sa.Column('channel', sa.String(20), nullable=False),
                    sa.Column('subject', sa.String(180), nullable=False), sa.Column('content', sa.Text(), nullable=False))
    op.create_table('inbox_threads', *base(), sa.Column('channel', sa.String(20), nullable=False), sa.Column('address', sa.String(254), nullable=False),
                    sa.Column('contact_id', sa.String(36), sa.ForeignKey('contacts.id')), sa.Column('subject', sa.String(180), nullable=False),
                    sa.UniqueConstraint('workspace_id', 'channel', 'address'))
    op.create_index('ix_inbox_threads_contact_id', 'inbox_threads', ['contact_id'])
    op.create_table('inbox_messages', *base(), sa.Column('thread_id', sa.String(36), sa.ForeignKey('inbox_threads.id'), nullable=False),
                    sa.Column('direction', sa.String(10), nullable=False), sa.Column('content', sa.Text(), nullable=False),
                    sa.Column('subject', sa.String(180), nullable=False), sa.Column('status', sa.String(20), nullable=False),
                    sa.Column('idempotency_key', sa.String(180), nullable=False), sa.Column('provider_id', sa.String(180)),
                    sa.Column('sent_by_id', sa.String(36), sa.ForeignKey('users.id')), sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('error', sa.String(500)), sa.UniqueConstraint('workspace_id', 'idempotency_key'))
    for column in ('thread_id', 'scheduled_at'):
        op.create_index('ix_inbox_messages_' + column, 'inbox_messages', [column])
    for table in ('message_templates', 'inbox_threads', 'inbox_messages'):
        op.create_index('ix_' + table + '_workspace_id', table, ['workspace_id'])


def downgrade():
    for table in ('inbox_messages', 'inbox_threads', 'message_templates'): op.drop_table(table)
