"""Account/user-scoped saved contact views."""
from alembic import op
import sqlalchemy as sa
revision='20261021_contact_views'
down_revision='20261021_pipelines'
branch_labels=depends_on=None


def upgrade():
    op.create_table('saved_contact_views',sa.Column('id',sa.String(36),primary_key=True),
      sa.Column('workspace_id',sa.String(36),sa.ForeignKey('workspaces.id'),nullable=False),sa.Column('user_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
      sa.Column('name',sa.String(50),nullable=False),sa.Column('filters',sa.JSON(),nullable=False),
      sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
      sa.UniqueConstraint('workspace_id','user_id','name'))
    op.create_index('ix_saved_contact_views_workspace_id','saved_contact_views',['workspace_id'])


def downgrade():op.drop_table('saved_contact_views')
