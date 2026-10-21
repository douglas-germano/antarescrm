from pathlib import Path
from flask_migrate import upgrade, downgrade
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from app import create_app
from app.extensions import db
from app.models import Workspace


def test_migrations_preserve_existing_workspace_and_match_models(tmp_path):
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(tmp_path/'migration.sqlite'),
                      'SQLALCHEMY_ENGINE_OPTIONS': {}, 'RATELIMIT_ENABLED': False})
    directory = str(Path(__file__).resolve().parents[1]/'migrations')
    with app.app_context():
        upgrade(directory=directory, revision='7e314cb26226')
        db.session.execute(db.text("INSERT INTO workspaces (id,name,slug,timezone,created_at,updated_at) VALUES ('legacy', 'Existing agency', 'existing', 'America/Cuiaba', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        db.session.commit()
        upgrade(directory=directory)
        ws = db.session.get(Workspace, 'legacy')
        assert ws.active and ws.parent_workspace_id is None and ws.name == 'Existing agency'
        with db.engine.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), db.metadata) == []
        db.session.remove()
        downgrade(directory=directory, revision='7e314cb26226')
        upgrade(directory=directory)
        assert db.session.get(Workspace, 'legacy').name == 'Existing agency'
        db.session.remove(); db.engine.dispose()


def test_operations_upgrade_preserves_existing_form_and_rule(tmp_path):
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path/'populated.sqlite'),'SQLALCHEMY_ENGINE_OPTIONS':{},'RATELIMIT_ENABLED':False})
    directory=str(Path(__file__).resolve().parents[1]/'migrations')
    with app.app_context():
        upgrade(directory=directory,revision='20261021_workflows')
        db.session.execute(db.text("INSERT INTO workspaces (id,name,slug,timezone,active,created_at,updated_at) VALUES ('legacy','Internal','internal','America/Cuiaba',true,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        db.session.execute(db.text("INSERT INTO pipeline_stages (id,workspace_id,name,position,color,created_at,updated_at) VALUES ('stage','legacy','New',0,'#7542c6',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        db.session.execute(db.text("INSERT INTO lead_forms (id,workspace_id,name,headline,description,success_message,stage_id,source,active,created_at,updated_at) VALUES ('form','legacy','Internal form','Hello','Description','Thanks','stage','Site',false,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        db.session.execute(db.text("INSERT INTO automation_rules (id,workspace_id,name,event,task_title,due_days,active,required_tag,actions,created_at,updated_at) VALUES ('rule','legacy','Follow-up','form.submitted','Call',0,true,NULL,'[]',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        db.session.commit();upgrade(directory=directory)
        from app.models import LeadForm,AutomationRule
        form=db.session.get(LeadForm,'form');rule=db.session.get(AutomationRule,'rule')
        assert form.description=='Description' and form.fields==[] and not form.active
        assert rule.active and not rule.stop_on_reply and rule.conditions=={}
        db.session.remove();db.engine.dispose()
