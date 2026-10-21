"""Instagram comments as automation triggers and targets of replies."""
from alembic import op
import sqlalchemy as sa

revision = '20261021_instagram_comments'
down_revision = '20261021_instagram'
branch_labels = depends_on = None


def upgrade():
    op.create_table('instagram_comments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False, index=True),
        sa.Column('connection_id', sa.String(36), sa.ForeignKey('instagram_connections.id'), nullable=False),
        sa.Column('comment_id', sa.String(80), nullable=False, unique=True),
        sa.Column('media_id', sa.String(80)),
        sa.Column('from_id', sa.String(80), nullable=False),
        sa.Column('username', sa.String(150)),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('contact_id', sa.String(36), sa.ForeignKey('contacts.id')),
        sa.Column('replied_at', sa.DateTime(timezone=True)),
        sa.Column('private_replied_at', sa.DateTime(timezone=True)))
    op.create_index('ix_instagram_comments_from_id', 'instagram_comments', ['from_id'])
    op.create_index('ix_instagram_comments_contact_id', 'instagram_comments', ['contact_id'])


def downgrade():
    op.drop_table('instagram_comments')
