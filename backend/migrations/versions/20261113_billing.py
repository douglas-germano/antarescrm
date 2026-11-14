"""Subscriptions (Asaas) and idempotent billing webhook events."""

import sqlalchemy as sa
from alembic import op

revision = '20261113_billing'
down_revision = '20261111_api_tokens'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False, index=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('trial_ends_at', sa.DateTime(timezone=True)),
        sa.Column('past_due_since', sa.DateTime(timezone=True)),
        sa.Column('last_paid_at', sa.DateTime(timezone=True)),
        sa.Column('next_due_date', sa.Date()),
        sa.Column('asaas_customer_id', sa.String(64)),
        sa.Column('asaas_subscription_id', sa.String(64), unique=True),
        sa.Column('invoice_url', sa.String(500)),
        sa.UniqueConstraint('workspace_id'),
    )
    op.create_table(
        'billing_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('event_id', sa.String(80), nullable=False, unique=True),
        sa.Column('event_type', sa.String(60), nullable=False),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), index=True),
    )


def downgrade():
    op.drop_table('billing_events')
    op.drop_table('subscriptions')
