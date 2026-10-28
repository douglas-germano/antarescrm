"""Unify email and WhatsApp campaigns, preserving existing email records."""
from alembic import op
import sqlalchemy as sa

revision = '20261022_campaign_channels'
down_revision = '20261022_brevo'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('email_campaigns', sa.Column('channel', sa.String(20), nullable=False, server_default='email'))
    with op.batch_alter_table('email_campaigns') as batch:
        batch.alter_column('channel', existing_type=sa.String(20), server_default=None)
        batch.add_column(sa.Column('whatsapp_connection_id', sa.String(36)))
        batch.create_foreign_key('fk_campaign_whatsapp_connection', 'whatsapp_connections', ['whatsapp_connection_id'], ['id'])
    with op.batch_alter_table('campaign_recipients') as batch:
        batch.alter_column('email', existing_type=sa.String(254), nullable=True)
        batch.add_column(sa.Column('phone', sa.String(20)))
        batch.add_column(sa.Column('message_id', sa.String(36)))
        batch.create_foreign_key('fk_campaign_recipient_message', 'inbox_messages', ['message_id'], ['id'])
        batch.create_unique_constraint('uq_campaign_recipient_message', ['message_id'])
        batch.create_unique_constraint('uq_campaign_recipient_phone', ['campaign_id', 'phone'])


def downgrade():
    # WhatsApp-only records have no email equivalent.
    op.execute("DELETE FROM campaign_recipients WHERE campaign_id IN (SELECT id FROM email_campaigns WHERE channel = 'whatsapp')")
    op.execute("DELETE FROM email_campaigns WHERE channel = 'whatsapp'")
    with op.batch_alter_table('campaign_recipients') as batch:
        batch.drop_constraint('uq_campaign_recipient_phone', type_='unique')
        batch.drop_constraint('uq_campaign_recipient_message', type_='unique')
        batch.drop_constraint('fk_campaign_recipient_message', type_='foreignkey')
        batch.drop_column('message_id')
        batch.drop_column('phone')
        batch.alter_column('email', existing_type=sa.String(254), nullable=False)
    with op.batch_alter_table('email_campaigns') as batch:
        batch.drop_constraint('fk_campaign_whatsapp_connection', type_='foreignkey')
        batch.drop_column('whatsapp_connection_id')
        batch.drop_column('channel')
