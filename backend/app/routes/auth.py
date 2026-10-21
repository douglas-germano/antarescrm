from flask import Blueprint, current_app, g
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity, get_jwt
from werkzeug.security import generate_password_hash, check_password_hash
from ..extensions import db, limiter
from ..models import Workspace, User, PipelineStage
from ..schemas import RegisterSchema, LoginSchema, UserSchema, UserUpdateSchema, ProfileSchema, WorkspaceSchema
from ..common import require, APIError, payload, query, get, add, update, commit, page, audit, validate_timezone

bp = Blueprint('auth', __name__)

DEFAULT_STAGES = ['Novo lead', 'Qualificação', 'Reunião', 'Proposta', 'Negociação']


def tokens(user, workspace_id=None):
    workspace_id = workspace_id or user.workspace_id
    claims = {'ver': user.token_version, 'wid': workspace_id}
    return {'access_token': create_access_token(identity=user.id, additional_claims=claims),
            'refresh_token': create_refresh_token(identity=user.id, additional_claims=claims),
            'user': user.to_dict(), 'workspace': db.session.get(Workspace, workspace_id).to_dict()}


@bp.post('/auth/register')
@limiter.limit('5 per hour')
def register():
    if not current_app.config['ALLOW_REGISTRATION']:
        raise APIError('Cadastro público desativado.', 403)
    data = payload(RegisterSchema)
    workspace = Workspace(name=data['workspace_name'], slug=data['slug'])
    db.session.add(workspace)
    db.session.flush()
    user = User(workspace_id=workspace.id, name=data['name'], email=data['email'].lower(),
                password_hash=generate_password_hash(data['password']), role='owner', title='Proprietário')
    db.session.add(user)
    for i, name in enumerate(DEFAULT_STAGES):
        db.session.add(PipelineStage(workspace_id=workspace.id, name=name, position=i))
    db.session.commit()
    return tokens(user), 201


@bp.post('/auth/login')
@limiter.limit('10 per minute')
def login():
    data = payload(LoginSchema)
    workspace = Workspace.query.filter_by(slug=data['slug']).first()
    user = User.query.filter_by(workspace_id=workspace.id, email=data['email'].lower()).first() if workspace else None
    if not workspace or not workspace.active or not user or not check_password_hash(user.password_hash, data['password']) or not user.active:
        raise APIError('Workspace, e-mail ou senha inválidos.', 401)
    return tokens(user)


@bp.post('/auth/refresh')
@jwt_required(refresh=True)
def refresh():
    user = db.session.get(User, get_jwt_identity())
    return {'access_token': create_access_token(identity=user.id, additional_claims={'ver': user.token_version, 'wid': get_jwt().get('wid', user.workspace_id)})}


@bp.get('/auth/me')
@require()
def me():
    data = g.user.to_dict()
    data['home_role'] = data['role']
    data['role'] = g.role
    return {'user': data, 'workspace': db.session.get(Workspace, g.workspace_id).to_dict()}


@bp.patch('/auth/me')
@require()
def me_update():
    data = payload(ProfileSchema)
    new_password = data.pop('password', None)
    current = data.pop('current_password', None)
    if new_password:
        if not current or not check_password_hash(g.user.password_hash, current):
            raise APIError('A senha atual não confere.', 400)
        g.user.password_hash = generate_password_hash(new_password)
        g.user.token_version += 1
        audit('password_change', g.user)
    update(g.user, data)
    return commit(g.user)


@bp.post('/auth/logout')
@require()
def logout():
    g.user.token_version += 1
    audit('logout_all_sessions', g.user)
    db.session.commit()
    return {'message': 'Sessões encerradas.'}


@bp.patch('/workspace')
@require('owner', 'admin')
def workspace_update():
    data = payload(WorkspaceSchema)
    if 'timezone' in data:
        validate_timezone(data['timezone'])
    row = db.session.get(Workspace, g.workspace_id)
    update(row, data)
    return commit(row)


@bp.get('/users')
@require()
def users():
    from ..access import account_users
    rows = account_users(g.workspace_id)
    return page(User.query.filter(User.id.in_([u.id for u in rows])).order_by(User.name))


@bp.post('/users')
@require('owner', 'admin')
def user_create():
    data = payload(UserSchema)
    data['email'] = data['email'].lower()
    data['password_hash'] = generate_password_hash(data.pop('password'))
    return commit(add(User, data), 201)


@bp.patch('/users/<uuid:user_id>')
@require('owner', 'admin')
def user_update(user_id):
    user = get(User, user_id)
    data = payload(UserUpdateSchema)
    if user.role == 'owner' and ('role' in data or data.get('active') is False):
        raise APIError('O proprietário não pode ser desativado ou ter o perfil alterado.')
    if user.id == g.user.id and data.get('active') is False:
        raise APIError('Você não pode desativar seu próprio acesso.')
    if 'password' in data:
        data['password_hash'] = generate_password_hash(data.pop('password'))
    if any(k in data for k in ('active', 'password_hash')):
        user.token_version += 1
    update(user, data)
    return commit(user)
