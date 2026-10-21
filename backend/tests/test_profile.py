import pytest
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash
from app import create_app
from app.extensions import db
from app.models import Workspace, User


@pytest.fixture()
def member_client():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SQLALCHEMY_ENGINE_OPTIONS': {},
                      'JWT_SECRET_KEY': 'test-only-key-with-more-than-thirty-two-characters', 'RATELIMIT_ENABLED': False})
    with app.app_context():
        db.create_all()
        workspace = Workspace(name='W', slug='profile-test')
        db.session.add(workspace); db.session.flush()
        user = User(workspace_id=workspace.id, name='Ana', email='ana@example.invalid', role='member',
                    password_hash=generate_password_hash('senha-atual-123'))
        db.session.add(user); db.session.commit()
        token = create_access_token(identity=user.id, additional_claims={'ver': 0})
        yield app.test_client(), {'Authorization': 'Bearer ' + token}, user.id
        db.session.remove(); db.drop_all()


def test_member_edits_own_profile(member_client):
    client, headers, _ = member_client
    response = client.patch('/api/v1/auth/me', json={'name': 'Ana Souza', 'title': 'SDR'}, headers=headers)
    assert response.status_code == 200
    assert response.get_json()['name'] == 'Ana Souza' and response.get_json()['title'] == 'SDR'


def test_profile_cannot_change_role(member_client):
    client, headers, _ = member_client
    assert client.patch('/api/v1/auth/me', json={'role': 'admin'}, headers=headers).status_code == 422


def test_password_change_requires_current_password(member_client):
    client, headers, user_id = member_client
    wrong = client.patch('/api/v1/auth/me', json={'password': 'nova-senha-1234', 'current_password': 'errada'}, headers=headers)
    assert wrong.status_code == 400
    ok = client.patch('/api/v1/auth/me', json={'password': 'nova-senha-1234', 'current_password': 'senha-atual-123'}, headers=headers)
    assert ok.status_code == 200
    assert db.session.get(User, user_id).token_version == 1
