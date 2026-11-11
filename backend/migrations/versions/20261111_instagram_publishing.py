"""Several Instagram accounts per workspace, post publishing, uploaded media and metric snapshots."""

import sqlalchemy as sa
from alembic import op

revision = '20261111_instagram_publishing'
down_revision = '20261106_campaign_archive'
branch_labels = None
depends_on = None
NAMING = {'uq': '%(table_name)s_%(column_0_name)s_key'}


def base():
    return [
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False, index=True),
    ]


def upgrade():
    # One Instagram profile still belongs to a single workspace (instagram_id stays unique). The constraint was
    # created unnamed: the convention gives it PostgreSQL's default name, also when SQLite reflects it.
    with op.batch_alter_table('instagram_connections', naming_convention=NAMING) as batch:
        batch.drop_constraint('instagram_connections_workspace_id_key', type_='unique')
        batch.add_column(sa.Column('scopes', sa.Text()))
    op.create_table(
        'instagram_media',
        *base(),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('kind', sa.String(10), nullable=False),
        sa.Column('content_type', sa.String(80), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('storage_key', sa.String(255), nullable=False),
        sa.Column('public_token', sa.String(64), nullable=False, unique=True),
        sa.Column('created_by_id', sa.String(36), sa.ForeignKey('users.id')),
    )
    op.create_table(
        'instagram_posts',
        *base(),
        sa.Column(
            'connection_id', sa.String(36), sa.ForeignKey('instagram_connections.id'), nullable=False, index=True
        ),
        sa.Column('media_type', sa.String(20), nullable=False),
        sa.Column('caption', sa.Text(), nullable=False, server_default=''),
        sa.Column('items', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, index=True),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), index=True),
        sa.Column('containers', sa.JSON(), nullable=False),
        sa.Column('processing_since', sa.DateTime(timezone=True)),
        sa.Column('ig_media_id', sa.String(80)),
        sa.Column('permalink', sa.Text()),
        sa.Column('published_at', sa.DateTime(timezone=True)),
        sa.Column('error', sa.String(500)),
        sa.Column('created_by_id', sa.String(36), sa.ForeignKey('users.id')),
    )
    op.create_table(
        'instagram_insight_snapshots',
        *base(),
        sa.Column('connection_id', sa.String(36), sa.ForeignKey('instagram_connections.id'), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('period', sa.Integer(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.UniqueConstraint('connection_id', 'day', 'period'),
    )


def downgrade():
    for name in ('instagram_insight_snapshots', 'instagram_posts', 'instagram_media'):
        op.drop_table(name)
    with op.batch_alter_table('instagram_connections', naming_convention=NAMING) as batch:
        batch.drop_column('scopes')
        batch.create_unique_constraint('instagram_connections_workspace_id_key', ['workspace_id'])
