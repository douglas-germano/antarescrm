"""Name and profile picture of the connected Instagram account."""
from alembic import op
import sqlalchemy as sa

revision = '20261021_instagram_profile'
down_revision = '20261021_instagram_comments'
branch_labels = depends_on = None


def upgrade():
    op.add_column('instagram_connections', sa.Column('name', sa.String(150)))
    op.add_column('instagram_connections', sa.Column('profile_picture_url', sa.Text()))
    op.add_column('instagram_connections', sa.Column('profile_synced_at', sa.DateTime(timezone=True)))


def downgrade():
    for column in ('profile_synced_at', 'profile_picture_url', 'name'):
        op.drop_column('instagram_connections', column)
