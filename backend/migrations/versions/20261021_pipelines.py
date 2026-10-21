"""Multiple internal sales pipelines; legacy stages remain in the primary pipeline."""
from alembic import op
import sqlalchemy as sa
revision = '20261021_pipelines'
down_revision = '20261021_operations'
branch_labels = depends_on = None


def upgrade():
    op.create_table('pipelines',sa.Column('id',sa.String(36),primary_key=True),sa.Column('workspace_id',sa.String(36),sa.ForeignKey('workspaces.id'),nullable=False),
        sa.Column('name',sa.String(150),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint('workspace_id','name'))
    op.create_index('ix_pipelines_workspace_id','pipelines',['workspace_id'])
    constraints = sa.inspect(op.get_bind()).get_unique_constraints('pipeline_stages')
    previous = next(c for c in constraints if c['column_names'] == ['workspace_id','name'])
    with op.batch_alter_table('pipeline_stages', naming_convention={'uq':'uq_%(table_name)s_%(column_0_name)s_%(column_1_name)s'}) as batch:
        batch.add_column(sa.Column('pipeline_id',sa.String(36)))
        batch.create_foreign_key('fk_stage_pipeline','pipelines',['pipeline_id'],['id'])
        batch.drop_constraint(previous['name'] or 'uq_pipeline_stages_workspace_id_name',type_='unique')
        batch.create_unique_constraint('uq_stage_pipeline_name',['workspace_id','pipeline_id','name'])
        batch.create_index('ix_pipeline_stages_pipeline_id',['pipeline_id'])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT workspace_id, name FROM pipeline_stages GROUP BY workspace_id, name HAVING count(*) > 1')).first():
        raise RuntimeError('Há nomes de etapas repetidos entre funis. Renomeie-os antes de reverter a migração.')
    with op.batch_alter_table('pipeline_stages') as batch:
        batch.drop_index('ix_pipeline_stages_pipeline_id')
        batch.drop_constraint('uq_stage_pipeline_name',type_='unique')
        batch.drop_constraint('fk_stage_pipeline',type_='foreignkey')
        batch.drop_column('pipeline_id')
        batch.create_unique_constraint('uq_pipeline_stages_workspace_id_name',['workspace_id','name'])
    op.drop_table('pipelines')
