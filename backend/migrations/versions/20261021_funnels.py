"""Page funnels (steps, blocks, events) and form design/settings."""
import sqlalchemy as sa
from alembic import op

revision = '20261021_funnels'
down_revision = '20261021_projects'
branch_labels = depends_on = None


def base():
    return [sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False, index=True)]


def upgrade():
    op.create_table('funnels', *base(),
        sa.Column('name', sa.String(150), nullable=False), sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False), sa.Column('theme', sa.JSON(), nullable=False))
    op.create_table('funnel_steps', *base(),
        sa.Column('funnel_id', sa.String(36), sa.ForeignKey('funnels.id'), nullable=False, index=True),
        sa.Column('name', sa.String(150), nullable=False), sa.Column('slug', sa.String(60), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False), sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('blocks', sa.JSON(), nullable=False), sa.Column('settings', sa.JSON(), nullable=False),
        sa.UniqueConstraint('funnel_id', 'slug', name='uq_funnel_step_slug'))
    op.create_table('funnel_events', *base(),
        sa.Column('funnel_id', sa.String(36), sa.ForeignKey('funnels.id'), nullable=False, index=True),
        sa.Column('step_id', sa.String(36), sa.ForeignKey('funnel_steps.id'), nullable=False, index=True),
        sa.Column('kind', sa.String(20), nullable=False), sa.Column('visitor_id', sa.String(36), nullable=False))
    with op.batch_alter_table('lead_forms', schema=None) as batch_op:
        batch_op.add_column(sa.Column('design', sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
        batch_op.add_column(sa.Column('settings', sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    if op.get_bind().dialect.name != 'sqlite':
        for column in ('design', 'settings'):
            op.alter_column('lead_forms', column, server_default=None)


def downgrade():
    with op.batch_alter_table('lead_forms', schema=None) as batch_op:
        batch_op.drop_column('settings')
        batch_op.drop_column('design')
    op.drop_table('funnel_events')
    op.drop_table('funnel_steps')
    op.drop_table('funnels')
