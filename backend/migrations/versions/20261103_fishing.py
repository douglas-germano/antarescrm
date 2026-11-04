"""Manual-link prospecting copilot, disabled by default."""
from alembic import op
import sqlalchemy as sa

revision = '20261103_fishing'
down_revision = '20261028_inbox_thread_status'
branch_labels = None
depends_on = None


def base():
    return [sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)]


def upgrade():
    op.create_table('fishing_settings', *base(),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('brand_name', sa.String(150), nullable=False),
        sa.Column('brand_profile', sa.Text(), nullable=False),
        sa.Column('tone', sa.String(300), nullable=False),
        sa.Column('examples', sa.Text(), nullable=False),
        sa.Column('allowed_topics', sa.Text(), nullable=False),
        sa.Column('forbidden_words', sa.JSON(), nullable=False),
        sa.Column('blocked_authors', sa.JSON(), nullable=False),
        sa.Column('own_username', sa.String(30), nullable=False),
        sa.Column('objective', sa.String(30), nullable=False),
        sa.Column('score_threshold', sa.Integer(), nullable=False),
        sa.Column('daily_limit', sa.Integer(), nullable=False),
        sa.Column('daily_ai_limit', sa.Integer(), nullable=False),
        sa.UniqueConstraint('workspace_id'))
    op.create_table('fishing_posts', *base(),
        sa.Column('url', sa.String(300), nullable=False),
        sa.Column('media_id', sa.String(100), nullable=False),
        sa.Column('author', sa.String(30), nullable=False),
        sa.Column('caption', sa.Text(), nullable=False),
        sa.Column('image_data', sa.Text()),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('score', sa.Integer()),
        sa.Column('reason', sa.String(300)),
        sa.Column('summary', sa.String(600)),
        sa.Column('error', sa.String(300)),
        *[sa.Column(name, sa.DateTime(timezone=True)) for name in (
            'queued_at', 'processing_at', 'opened_at', 'published_at', 'decided_at')],
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id')),
        sa.Column('selected_draft_id', sa.String(36)),
        sa.Column('published_text', sa.String(220)),
        sa.Column('edited', sa.Boolean(), nullable=False),
        sa.UniqueConstraint('workspace_id', 'media_id'))
    op.create_index('ix_fishing_posts_workspace_status', 'fishing_posts', ['workspace_id', 'status'])
    op.create_table('fishing_drafts', *base(),
        sa.Column('post_id', sa.String(36), sa.ForeignKey('fishing_posts.id'), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('text', sa.String(220), nullable=False),
        sa.Column('generation', sa.Integer(), nullable=False))
    op.create_index('ix_fishing_drafts_post_id', 'fishing_drafts', ['post_id'])
    op.create_table('fishing_usage', *base(),
        sa.Column('post_id', sa.String(36), sa.ForeignKey('fishing_posts.id'), nullable=False),
        sa.Column('model', sa.String(150), nullable=False),
        sa.Column('phase', sa.String(20), nullable=False),
        sa.Column('tokens', sa.Integer(), nullable=False),
        sa.Column('cost_usd', sa.Numeric(16, 8)))
    for table in ('fishing_settings', 'fishing_posts', 'fishing_drafts', 'fishing_usage'):
        op.create_index('ix_' + table + '_workspace_id', table, ['workspace_id'])


def downgrade():
    for table in ('fishing_usage', 'fishing_drafts', 'fishing_posts', 'fishing_settings'):
        op.drop_table(table)
