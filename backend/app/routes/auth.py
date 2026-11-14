import secrets

from flask import Blueprint, current_app, g
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt, get_jwt_identity, jwt_required
from marshmallow import fields as f
from marshmallow import validate
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

from ..access import account_users
from ..common import APIError, add, audit, commit, get, page, payload, require, update, validate_timezone
from ..extensions import db, limiter
from ..models import PipelineStage, User, UserAccessToken, Workspace
from ..schemas import (
    LoginSchema,
    ProfileSchema,
    RegisterSchema,
    StrictSchema,
    UserSchema,
    UserUpdateSchema,
    WorkspaceSchema,
    choice,
    text,
)
from ..services import access_email, brevo
from ..services.billing import start_trial

bp = Blueprint('auth', __name__)

DEFAULT_STAGES = ['Novo lead', 'Qualificação', 'Reunião', 'Proposta', 'Negociação']


class ForgotSchema(StrictSchema):
    slug = text(80, required=True)
    email = f.Email(required=True, validate=validate.Length(max=254))


class AccessSchema(StrictSchema):
    token = f.String(required=True, load_only=True, validate=validate.Length(min=40, max=100))
    password = f.String(required=True, load_only=True, validate=validate.Length(min=10, max=128))


class InviteSchema(StrictSchema):
    name = text(150, required=True)
    email = f.Email(required=True, validate=validate.Length(max=254))
    role = choice('admin member', load_default='member')
    title = text(80, allow_none=True)


@bp.post('/auth/forgot-password')
@limiter.limit('5 per minute;20 per hour')
def forgot_password():
    data = payload(ForgotSchema)
    return access_email.request_reset(data['slug'], data['email'])


@bp.post('/auth/accept-access')
@limiter.limit('10 per minute')
def accept_access():
    data = payload(AccessSchema)
    return access_email.accept(data['token'], data['password'])


@bp.post('/users/invitations')
@require('owner', 'admin')
@limiter.limit('10 per hour')
def invite():
    data = payload(InviteSchema)
    brevo.access_sender(g.workspace_id)
    email = data.pop('email').strip().lower()
    user = (
        User.query.filter(User.workspace_id == g.workspace_id, func.lower(User.email) == email)
        .with_for_update()
        .first()
    )
    if user:
        pending = UserAccessToken.query.filter_by(user_id=user.id, purpose='invite').first()
        if user.active or user.role == 'owner' or not pending:
            raise APIError('Este e-mail já tem um perfil. Edite o acesso existente.', 409)
    else:
        user = add(
            User,
            {
                **data,
                'email': email,
                'active': False,
                'password_hash': generate_password_hash(secrets.token_urlsafe(32)),
            },
        )
    result = access_email.issue(user, 'invite')
    audit('user_invite', user)
    db.session.commit()
    return {'user': user.to_dict(), 'delivery_status': result.delivery_status}, 201


def tokens(user, workspace_id=None):
    workspace_id = workspace_id or user.workspace_id
    claims = {'ver': user.token_version, 'wid': workspace_id}
    return {
        'access_token': create_access_token(identity=user.id, additional_claims=claims),
        'refresh_token': create_refresh_token(identity=user.id, additional_claims=claims),
        'user': user.to_dict(),
        'workspace': db.session.get(Workspace, workspace_id).to_dict(),
    }


@bp.post('/auth/register')
@limiter.limit('5 per hour')
def register():
    if not current_app.config['ALLOW_REGISTRATION']:
        raise APIError('Cadastro público desativado.', 403)
    data = payload(RegisterSchema)
    workspace = Workspace(name=data['workspace_name'], slug=data['slug'])
    db.session.add(workspace)
    db.session.flush()
    user = User(
        workspace_id=workspace.id,
        name=data['name'],
        email=data['email'].lower(),
        password_hash=generate_password_hash(data['password']),
        role='owner',
        title='Proprietário',
    )
    db.session.add(user)
    start_trial(workspace.id)
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
    if (
        not workspace
        or not workspace.active
        or not user
        or not check_password_hash(user.password_hash, data['password'])
        or not user.active
    ):
        raise APIError('Workspace, e-mail ou senha inválidos.', 401)
    return tokens(user)


@bp.post('/auth/refresh')
@jwt_required(refresh=True)
def refresh():
    user = db.session.get(User, get_jwt_identity())
    return {
        'access_token': create_access_token(
            identity=user.id,
            additional_claims={'ver': user.token_version, 'wid': get_jwt().get('wid', user.workspace_id)},
        )
    }


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
    email = (data.pop('email', None) or '').strip().lower()
    if email and email != g.user.email.lower():
        # The e-mail is the login, so changing it needs the current password, like changing the password does.
        if not current or not check_password_hash(g.user.password_hash, current):
            raise APIError('A senha atual não confere.', 400)
        taken = User.query.filter(
            User.workspace_id == g.user.workspace_id, func.lower(User.email) == email, User.id != g.user.id
        ).first()
        if taken:
            raise APIError('Este e-mail já é usado por outra pessoa desta conta.', 409)
        audit('email_change', g.user, {'from': g.user.email, 'to': email})
        g.user.email = email
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

    rows = account_users(g.workspace_id)
    result = page(User.query.filter(User.id.in_([u.id for u in rows])).order_by(User.name))
    pending = {
        row.user_id
        for row in UserAccessToken.query.filter_by(workspace_id=g.workspace_id, purpose='invite', consumed_at=None)
    }
    for item in result['items']:
        item['invite_pending'] = item['id'] in pending and not item['active']
    return result


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
