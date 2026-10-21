"""Custom fields and tags for CRM records."""
from alembic import op
import sqlalchemy as sa
revision = '20261021_crm_fields'
down_revision = '20261020_growth'
branch_labels = depends_on = None


def upgrade():
    for table in ('contacts', 'companies'):
        op.add_column(table, sa.Column('tags', sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        op.add_column(table, sa.Column('custom_fields', sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
        if op.get_bind().dialect.name != 'sqlite':
            op.alter_column(table, 'tags', server_default=None)
            op.alter_column(table, 'custom_fields', server_default=None)


def downgrade():
    for table in ('contacts', 'companies'):
        op.drop_column(table, 'custom_fields')
        op.drop_column(table, 'tags')
