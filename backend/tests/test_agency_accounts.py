import pytest
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash
from app import create_app
from app.extensions import db
from app.models import Workspace, User, WorkspaceAccess, Contact, AuditLog


@pytest.fixture()
def env():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SQLALCHEMY_ENGINE_OPTIONS': {},
        'JWT_SECRET_KEY': 'test-only-key-with-more-than-thirty-two-characters', 'RATELIMIT_ENABLED': False,
        'ALLOW_REGISTRATION': False})
    with app.app_context():
        db.create_all()
        agency = Workspace(name='Agency', slug='agency')
        stranger = Workspace(name='Other agency', slug='stranger')
        db.session.add_all([agency, stranger]); db.session.flush()
        client = Workspace(name='Client A', slug='client-a', parent_workspace_id=agency.id)
        sibling = Workspace(name='Client B', slug='client-b', parent_workspace_id=agency.id)
        foreign = Workspace(name='Foreign', slug='foreign', parent_workspace_id=stranger.id)
        db.session.add_all([client, sibling, foreign]); db.session.flush()
        users = {}
        for key, ws, role in [('owner', agency, 'owner'), ('admin', agency, 'admin'), ('staff', agency, 'member'),
                              ('client', client, 'owner'), ('member', client, 'member'), ('stranger', stranger, 'owner')]:
            users[key] = User(workspace_id=ws.id, name=key, email=f'{key}@example.com',
                role=role, password_hash=generate_password_hash('test-password-123'))
        db.session.add_all(users.values())
        lead = Contact(workspace_id=client.id, name='Private client lead')
        db.session.add(lead); db.session.commit()
        def headers(key='owner', ws=None, legacy=False):
            claims = {'ver': users[key].token_version}
            if not legacy: claims['wid'] = (ws or db.session.get(Workspace, users[key].workspace_id)).id
            return {'Authorization': 'Bearer ' + create_access_token(identity=users[key].id, additional_claims=claims)}
        yield app.test_client(), {'agency': agency, 'client': client, 'sibling': sibling, 'foreign': foreign,
                                 'users': users, 'headers': headers, 'lead': lead}
        db.session.remove(); db.drop_all()


def test_legacy_session_and_agency_switch(env):
    client, d = env
    h = d['headers'](legacy=True)
    assert client.get('/api/v1/auth/me', headers=h).status_code == 200
    response = client.post('/api/v1/auth/switch', headers=h, json={'workspace_id': d['client'].id})
    assert response.status_code == 200
    h = {'Authorization': 'Bearer ' + response.json['access_token']}
    me = client.get('/api/v1/auth/me', headers=h).json
    assert me['workspace']['id'] == d['client'].id and me['user']['role'] == 'admin'
    assert client.get('/api/v1/contacts', headers=h).json['items'][0]['name'] == 'Private client lead'
    assert client.get('/api/v1/agency/accounts', headers=h).status_code == 403
    refreshed = client.post('/api/v1/auth/refresh', headers={'Authorization': 'Bearer ' + response.json['refresh_token']})
    assert refreshed.status_code == 200
    assert client.get('/api/v1/auth/me', headers={'Authorization': 'Bearer ' + refreshed.json['access_token']}).json['workspace']['id'] == d['client'].id


def test_client_cannot_access_agency_sibling_or_foreign(env):
    client, d = env
    h = d['headers']('client')
    for ws in [d['agency'], d['sibling'], d['foreign']]:
        assert client.post('/api/v1/auth/switch', headers=h, json={'workspace_id': ws.id}).status_code == 404
    assert client.get('/api/v1/agency/accounts', headers=h).status_code == 403
    assert len(client.get('/api/v1/auth/workspaces', headers=h).json['items']) == 1
    assert client.get('/api/v1/contacts/' + d['lead'].id, headers=d['headers']('owner')).status_code == 404


@pytest.mark.parametrize('key', ['owner', 'admin'])
def test_agency_admin_only_sees_own_clients(env, key):
    client, d = env
    result = client.get('/api/v1/agency/accounts', headers=d['headers'](key))
    assert {x['id'] for x in result.json['items']} == {d['client'].id, d['sibling'].id}
    assert client.patch('/api/v1/agency/accounts/' + d['foreign'].id, headers=d['headers'](key), json={'name': 'Intrusion'}).status_code == 404
    assert client.post('/api/v1/auth/switch', headers=d['headers'](key), json={'workspace_id': d['foreign'].id}).status_code == 404


def test_member_cannot_manage_users_or_settings(env):
    client, d = env
    for key in ['staff', 'member']:
        h = d['headers'](key)
        assert client.patch('/api/v1/workspace', headers=h, json={'name': 'changed'}).status_code == 403
        assert client.post('/api/v1/users', headers=h, json={'name': 'bad', 'email': 'x@example.com', 'password': 'long-password'}).status_code == 403
        assert client.patch('/api/v1/users/' + d['users'][key].id, headers=h, json={'role': 'admin'}).status_code == 403
        assert client.get('/api/v1/agency/accounts', headers=h).status_code == 403


def test_explicit_staff_access_and_immediate_revocation(env):
    client, d = env
    endpoint = '/api/v1/agency/accounts/' + d['client'].id + '/access'
    staff_h = d['headers']('staff')
    assert client.post('/api/v1/auth/switch', headers=staff_h, json={'workspace_id': d['client'].id}).status_code == 404
    assert client.post(endpoint, headers=d['headers'](), json={'user_id': d['users']['staff'].id, 'role': 'member'}).status_code == 200
    switched = client.post('/api/v1/auth/switch', headers=staff_h, json={'workspace_id': d['client'].id}).json
    scoped = {'Authorization': 'Bearer ' + switched['access_token']}
    assert client.get('/api/v1/contacts', headers=scoped).status_code == 200
    assert client.patch('/api/v1/workspace', headers=scoped, json={'name': 'bad'}).status_code == 403
    assert client.post('/api/v1/tasks', headers=scoped, json={'title': 'Client task'}).status_code == 201
    assert client.delete(endpoint + '/' + d['users']['staff'].id, headers=d['headers']()).status_code == 204
    assert client.get('/api/v1/contacts', headers=scoped).status_code == 401
    assert client.post('/api/v1/auth/refresh', headers={'Authorization': 'Bearer ' + switched['refresh_token']}).status_code == 401
    assert client.get('/api/v1/auth/me', headers=staff_h).status_code == 200


def test_client_cannot_grant_self_agency_access_even_with_malformed_row(env):
    client, d = env
    db.session.add(WorkspaceAccess(workspace_id=d['sibling'].id, user_id=d['users']['client'].id, role='admin')); db.session.commit()
    assert client.post('/api/v1/auth/switch', headers=d['headers']('client'), json={'workspace_id': d['sibling'].id}).status_code == 404


def test_grant_only_active_members_of_same_agency(env):
    client, d = env
    endpoint = '/api/v1/agency/accounts/' + d['client'].id + '/access'
    for key in ['owner', 'client', 'stranger']:
        assert client.post(endpoint, headers=d['headers'](), json={'user_id': d['users'][key].id, 'role': 'admin'}).status_code == 422
    assert WorkspaceAccess.query.count() == 0


def test_stale_tab_cannot_read_or_write_other_selected_account(env):
    client, d = env
    h = dict(d['headers']('owner', d['client']), **{'X-Workspace-ID': d['agency'].id})
    for method, path, body in [('get', '/contacts', None), ('post', '/contacts', {'name': 'Wrong account'})]:
        result = getattr(client, method)('/api/v1' + path, headers=h, json=body)
        assert result.status_code == 409 and result.json['error']['code'] == 'account_changed'
    assert Contact.query.count() == 1


def test_create_client_owner_defaults_and_duplicate_transaction(env):
    client, d = env
    body = {'workspace_name': 'New client', 'slug': 'new-client', 'name': 'Client Owner', 'email': 'new@example.com', 'password': 'long-client-password', 'timezone': 'America/Cuiaba'}
    result = client.post('/api/v1/agency/accounts', headers=d['headers'](), json=body)
    assert result.status_code == 201
    row = db.session.get(Workspace, result.json['id'])
    assert row.parent_workspace_id == d['agency'].id and row.active
    login = client.post('/api/v1/auth/login', json={'slug': row.slug, 'email': body['email'], 'password': body['password']})
    assert login.status_code == 200 and login.json['user']['role'] == 'owner'
    assert 'password' not in result.json and 'password_hash' not in login.json['user']
    count = User.query.count()
    assert client.post('/api/v1/agency/accounts', headers=d['headers'](), json=body).status_code == 409
    assert User.query.count() == count
    assert AuditLog.query.filter_by(action='create_client_account').count() == 1


def test_client_admin_cannot_edit_agency_identity(env):
    client, d = env
    result = client.patch('/api/v1/users/' + d['users']['owner'].id, headers=d['headers']('client'), json={'password': 'stolen-password-123'})
    assert result.status_code == 404
    assert client.patch('/api/v1/users/' + d['users']['client'].id, headers=d['headers']('client'), json={'role': 'admin'}).status_code == 400


def test_suspension_blocks_client_and_agency_sessions(env):
    client, d = env
    h = d['headers']('client')
    agency_scoped = d['headers']('owner', d['client'])
    response = client.patch('/api/v1/agency/accounts/' + d['client'].id, headers=d['headers'](), json={'active': False})
    assert response.status_code == 200
    assert client.get('/api/v1/contacts', headers=h).status_code == 401
    assert client.get('/api/v1/contacts', headers=agency_scoped).status_code == 401
    assert client.post('/api/v1/auth/login', json={'slug': 'client-a', 'email': 'client@example.com', 'password': 'test-password-123'}).status_code == 401


def test_owner_cannot_be_disabled_or_demoted(env):
    client, d = env
    for body in [{'active': False}, {'role': 'member'}]:
        assert client.patch('/api/v1/users/' + d['users']['owner'].id, headers=d['headers']('admin'), json=body).status_code == 400
