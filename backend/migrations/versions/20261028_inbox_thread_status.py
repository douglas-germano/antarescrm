"""Instagram and e-mail conversations can be closed and assigned, like WhatsApp ones."""

from alembic import op
import sqlalchemy as sa

revision = '20261028_inbox_thread_status'
down_revision = '20261028_history_sync'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('inbox_threads') as batch:
        batch.add_column(sa.Column('status', sa.String(20), nullable=False, server_default='open'))
        batch.add_column(sa.Column('assigned_to_id', sa.String(36), nullable=True))
        batch.create_foreign_key('fk_inbox_threads_assigned_to_id_users', 'users', ['assigned_to_id'], ['id'])


def downgrade():
    with op.batch_alter_table('inbox_threads') as batch:
        batch.drop_constraint('fk_inbox_threads_assigned_to_id_users', type_='foreignkey')
        batch.drop_column('assigned_to_id')
        batch.drop_column('status')
