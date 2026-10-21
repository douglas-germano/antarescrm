"""Win probability per pipeline stage, for weighted forecasts."""
from alembic import op
import sqlalchemy as sa
revision='20261021_stage_probability'
down_revision='20261021_contact_views'
branch_labels=depends_on=None


def upgrade():
    op.add_column('pipeline_stages',sa.Column('probability',sa.Integer(),nullable=True))


def downgrade():
    op.drop_column('pipeline_stages','probability')
