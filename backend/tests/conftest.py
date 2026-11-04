"""Isolated application fixtures shared by every domain test."""

import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import pytest
import requests
from app import create_app
from app.extensions import db
from app.models import AutomationRule, LeadForm, PipelineStage, User, Workspace
from flask_jwt_extended import create_access_token
from flask_migrate import upgrade


@pytest.fixture()
def env():
    app = create_app(
        {
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'SQLALCHEMY_ENGINE_OPTIONS': {},
            'JWT_SECRET_KEY': 'test-only-key-with-more-than-thirty-two-characters',
            'RATELIMIT_ENABLED': False,
        }
    )
    with app.app_context():
        db.create_all()
        ws = Workspace(name='Client', slug='client', timezone='America/Cuiaba')
        other = Workspace(name='Other', slug='other')
        db.session.add_all([ws, other])
        db.session.flush()
        user = User(workspace_id=ws.id, name='Owner', email='owner@example.com', role='owner', password_hash='unused')
        member = User(
            workspace_id=ws.id, name='Member', email='member@example.com', role='member', password_hash='unused'
        )
        outsider = User(
            workspace_id=other.id, name='Other', email='other@example.com', role='owner', password_hash='unused'
        )
        stage = PipelineStage(workspace_id=ws.id, name='New', position=0)
        other_stage = PipelineStage(workspace_id=other.id, name='Other stage', position=0)
        db.session.add_all([user, member, outsider, stage, other_stage])
        db.session.flush()
        form = LeadForm(
            workspace_id=ws.id,
            name='Orçamento',
            headline='Solicite uma proposta',
            stage_id=stage.id,
            source='Campanha',
            active=True,
        )
        db.session.add(form)
        db.session.commit()

        def headers(u=user):
            return {'Authorization': 'Bearer ' + create_access_token(identity=u.id, additional_claims={'ver': 0})}

        yield (
            app.test_client(),
            {
                'ws': ws,
                'other': other,
                'owner': user,
                'member': member,
                'outsider': outsider,
                'stage': stage,
                'other_stage': other_stage,
                'form': form,
                'headers': headers,
            },
        )
        db.session.remove()
        db.drop_all()


URI = os.getenv('ANTARES_POSTGRES_TEST_URL')


@pytest.fixture()
def pg():
    if not URI:
        pytest.skip('Set ANTARES_POSTGRES_TEST_URL to a disposable antares_test_* database.')
    assert urlparse(URI).path.lstrip('/').startswith('antares_test_'), 'Refusing a non-test database'
    app = create_app(
        {
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': URI,
            'RATELIMIT_ENABLED': False,
            'JWT_SECRET_KEY': 'postgres-test-only-key-longer-than-thirty-two-characters',
        }
    )
    with app.app_context():
        upgrade(directory=str(Path(__file__).resolve().parents[1] / 'migrations'))
        ws = Workspace(name='Concurrency fixture', slug='fixture-' + str(uuid4()))
        db.session.add(ws)
        db.session.flush()
        user = User(workspace_id=ws.id, name='Test', email='test@example.com', role='owner', password_hash='unused')
        stage = PipelineStage(workspace_id=ws.id, name='New', position=0)
        db.session.add_all([user, stage])
        db.session.flush()
        form = LeadForm(workspace_id=ws.id, name='Test', headline='Test', stage_id=stage.id, active=True)
        rule = AutomationRule(
            workspace_id=ws.id, name='Rule', event='form.submitted', task_title='Call lead', active=True
        )
        db.session.add_all([form, rule])
        db.session.commit()
        yield app, ws.id, form.id, user.id
        db.session.remove()
        db.engine.dispose()


@pytest.fixture(autouse=True)
def no_external_http(monkeypatch):
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append(True)
        raise AssertionError('Real HTTP requests are forbidden in tests; use a fake provider adapter.')

    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)
    yield
    assert not attempts, 'A test attempted real HTTP instead of using a fake provider adapter.'


@pytest.fixture(autouse=True)
def no_profile_lookup(monkeypatch):
    from app.services.instagram import client

    monkeypatch.setattr(client, 'fetch_profile', lambda connection, scoped_id: None)
    monkeypatch.setattr(client, 'fetch_account', lambda token: None)
