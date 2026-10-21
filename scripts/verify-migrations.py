"""Verify upgrades against an isolated PostgreSQL database, never the configured CRM DB."""
import os
import secrets
import sys
from pathlib import Path
import psycopg
from psycopg import sql
from flask_migrate import upgrade, downgrade
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))
name = 'antares_migration_test_' + secrets.token_hex(6)
admin = os.getenv('MIGRATION_TEST_ADMIN_DSN', 'dbname=postgres')
with psycopg.connect(admin, autocommit=True) as connection:
    connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
try:
    from app import create_app
    from app.extensions import db
    app = create_app({'TESTING': True, 'RATELIMIT_ENABLED': False,
                      'SQLALCHEMY_DATABASE_URI': 'postgresql+psycopg://', 'SQLALCHEMY_ENGINE_OPTIONS': {'connect_args': psycopg.conninfo.conninfo_to_dict(admin, dbname=name)}})
    with app.app_context():
        directory = str(root / 'backend/migrations')
        upgrade(directory=directory, revision='7e314cb26226')
        db.session.execute(db.text("INSERT INTO workspaces (id,name,slug,timezone,created_at,updated_at) VALUES ('11111111-1111-4111-8111-111111111111','Preserved agency','preserved-agency','America/Cuiaba',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        db.session.execute(db.text("INSERT INTO contacts (id,workspace_id,name,email,archived,created_at,updated_at) VALUES ('22222222-2222-4222-8222-222222222222','11111111-1111-4111-8111-111111111111','Preserved contact','preserve@example.test',false,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        db.session.commit()
        for revision in ('head', '7e314cb26226', 'head'):
            db.session.remove()
            (downgrade if revision != 'head' else upgrade)(directory=directory, revision=revision)
            assert db.session.execute(db.text("SELECT name FROM contacts WHERE id='22222222-2222-4222-8222-222222222222'")).scalar() == 'Preserved contact'
            db.session.remove()
        with db.engine.connect() as connection:
            differences = compare_metadata(MigrationContext.configure(connection), db.metadata)
            assert not differences, differences
        db.session.remove()
        db.engine.dispose()
    print('PASS: populated baseline -> head -> baseline -> head; contact and workspace preserved; metadata matches.')
finally:
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
