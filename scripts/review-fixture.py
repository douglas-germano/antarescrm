from pathlib import Path
import sys, os, secrets
from datetime import date, timedelta
import psycopg
from psycopg import sql
from flask_migrate import upgrade, downgrade
from sqlalchemy import inspect
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata

root = Path(__file__).resolve().parents[1]
(root/'.review').mkdir(exist_ok=True)
sys.path.insert(0, str(root/'backend'))
name = 'antares_review_20261020_' + secrets.token_hex(3)
with psycopg.connect('dbname=postgres', autocommit=True) as conn:
    conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
os.environ['DATABASE_URL'] = 'postgresql+psycopg:///' + name
os.environ['APP_ENV'] = 'development'
os.environ['JWT_SECRET_KEY'] = 'review-only-key-do-not-use-in-production-20261020'
from app import create_app
from app.extensions import db
from app.models import Workspace, User, Contact, PipelineStage, Opportunity, Task, LeadForm, AutomationRule
from werkzeug.security import generate_password_hash
app = create_app({'TESTING': True, 'RATELIMIT_ENABLED': False})
with app.app_context():
    upgrade(directory=str(root/'backend/migrations'), revision='7e314cb26226')
    # Verify upgrade of a populated pre-agency schema, not just an empty database.
    db.session.execute(db.text("INSERT INTO workspaces (id,name,slug,timezone,created_at,updated_at) VALUES ('11111111-1111-4111-8111-111111111111', 'Agência de demonstração', 'agencia-demo', 'America/Cuiaba', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
    db.session.commit()
    upgrade(directory=str(root/'backend/migrations'))
    ws = db.session.get(Workspace, '11111111-1111-4111-8111-111111111111')
    assert ws.active and ws.parent_workspace_id is None
    diff = compare_metadata(MigrationContext.configure(db.engine.connect()), db.metadata)
    assert not diff, repr(diff)
    # Downgrade/upgrade with preserved original workspace data.
    db.session.remove()
    downgrade(directory=str(root/'backend/migrations'), revision='7e314cb26226')
    upgrade(directory=str(root/'backend/migrations'))
    agency = db.session.get(Workspace, '11111111-1111-4111-8111-111111111111')
    client_a = Workspace(name='Estúdio Aurora · demonstração', slug='aurora-demo', parent_workspace_id=agency.id, timezone='America/Cuiaba')
    client_b = Workspace(name='Clínica Horizonte · demonstração', slug='horizonte-demo', parent_workspace_id=agency.id, timezone='America/Cuiaba')
    db.session.add_all([client_a, client_b]); db.session.flush()
    password = generate_password_hash('Antares-review-only-2026')
    owner = User(name='Douglas · demonstração', email='admin@review.example', workspace_id=agency.id, role='owner', password_hash=password)
    staff = User(name='Marina · demonstração', email='marina@review.example', workspace_id=agency.id, role='member', password_hash=password)
    client_user = User(name='Cliente Aurora · demonstração', email='cliente@review.example', workspace_id=client_a.id, role='owner', password_hash=password)
    db.session.add_all([owner, staff, client_user]); db.session.flush()
    stages = []
    for workspace in [agency, client_a, client_b]:
        for pos, title in enumerate(['Novo lead', 'Qualificação', 'Reunião', 'Proposta', 'Negociação']):
            row = PipelineStage(workspace_id=workspace.id, name=title, position=pos, color='#7542c6'); db.session.add(row)
            if pos == 0: stages.append(row)
    db.session.flush()
    form = LeadForm(workspace_id=client_a.id, name='Diagnóstico de marketing', headline='Vamos conversar sobre o seu negócio?', description='Conte como podemos ajudar. Deixe seu contato para receber um retorno da nossa equipe.', stage_id=stages[1].id, source='Site Aurora', active=True)
    rule = AutomationRule(workspace_id=client_a.id, name='Primeiro atendimento do site', event='form.submitted', task_title='Entrar em contato com o novo lead', due_days=1, assignee_id=client_user.id, active=True)
    db.session.add_all([form, rule]); db.session.commit()
    (root/'.review/database-name').write_text(name)
    (root/'.review/form-id').write_text(form.id)
    (root/'.review/account-id').write_text(client_a.id)
    (root/'.review/migration-result.txt').write_text('PostgreSQL: upgrade populated baseline → head; metadata matches; downgrade → baseline → head; legacy workspace preserved.\n')
    print('PostgreSQL migration round trip: PASS; metadata parity: PASS; legacy data preserved: PASS')
