"""Single-use, short-lived access links. Only token hashes are stored."""

import hashlib
import secrets
from datetime import timedelta

from flask import current_app
from sqlalchemy import func
from werkzeug.security import generate_password_hash

from ..common import APIError
from ..extensions import db
from ..models import User, UserAccessToken, Workspace, now
from . import brevo


def issue(user, purpose):
    # Serialize requests for the same identity; repeated clicks cannot invalidate a newly mailed link.
    user = User.query.filter_by(id=user.id).with_for_update().one()
    recent = (
        UserAccessToken.query.filter_by(user_id=user.id, consumed_at=None)
        .order_by(UserAccessToken.created_at.desc())
        .first()
    )
    if recent and recent.created_at > now() - timedelta(seconds=60):
        return recent
    UserAccessToken.query.filter_by(user_id=user.id, consumed_at=None).update({'consumed_at': now()})
    token = secrets.token_urlsafe(32)
    row = UserAccessToken(
        workspace_id=user.workspace_id,
        user_id=user.id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        purpose=purpose,
        token_version=user.token_version,
        email=user.email,
        expires_at=now() + timedelta(minutes=30 if purpose == 'reset' else 1440),
    )
    db.session.add(row)
    db.session.commit()  # Persist the claim before external I/O; no automatic resend on ambiguous delivery.
    workspace = db.session.get(Workspace, user.workspace_id)
    link = current_app.config['APP_URL'] + '/definir-senha#token=' + token
    subject = 'Defina seu acesso ao Antares CRM' if purpose == 'invite' else 'Redefina sua senha do Antares CRM'
    content = f'Olá, {user.name}.\n\n{subject}:\n{link}\n\nConta: {workspace.slug}\nEste link é pessoal e pode ser usado uma única vez. '
    content += (
        'Ele expira em '
        + ('24 horas.' if purpose == 'invite' else '30 minutos.')
        + '\nSe você não solicitou este acesso, ignore este e-mail.'
    )
    try:
        brevo.send_access(user.workspace_id, user.email, user.name, subject, content)
        row.delivery_status = 'sent'
    except Exception as error:
        current_app.logger.warning('E-mail de acesso sem confirmação: %s', type(error).__name__)
        row.delivery_status = 'unknown'
    db.session.commit()
    return row


def request_reset(slug, email):
    workspace = Workspace.query.filter_by(slug=slug.strip().lower(), active=True).first()
    if workspace:
        user = User.query.filter(
            User.workspace_id == workspace.id, func.lower(User.email) == email.strip().lower(), User.active.is_(True)
        ).first()
        if user:
            try:
                brevo.access_sender(workspace.id)
                issue(user, 'reset')
            except APIError:
                db.session.rollback()
    # Identical response for nonexistent, inactive, unavailable and valid accounts.
    return {'message': 'Se os dados corresponderem a um acesso ativo, você receberá um link por e-mail.'}


def accept(token, password):
    digest = hashlib.sha256(token.encode()).hexdigest()
    row = UserAccessToken.query.filter_by(token_hash=digest).first()
    if not row or row.consumed_at or row.expires_at <= now():
        raise APIError('Link inválido ou expirado. Solicite um novo acesso.', 422)
    user = User.query.filter_by(id=row.user_id, workspace_id=row.workspace_id).with_for_update().first()
    row = UserAccessToken.query.filter_by(id=row.id).with_for_update().populate_existing().one()
    workspace = db.session.get(Workspace, row.workspace_id)
    if (
        not user
        or not workspace
        or not workspace.active
        or user.token_version != row.token_version
        or user.email != row.email
        or (row.purpose == 'reset' and not user.active)
    ):
        raise APIError('Link inválido ou expirado. Solicite um novo acesso.', 422)
    user.password_hash = generate_password_hash(password)
    user.token_version += 1
    if row.purpose == 'invite':
        user.active = True
    UserAccessToken.query.filter_by(user_id=user.id, consumed_at=None).update({'consumed_at': now()})
    db.session.commit()
    return {'message': 'Senha definida. Entre com seu e-mail e a nova senha.', 'slug': workspace.slug}
