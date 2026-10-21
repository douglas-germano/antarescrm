from functools import wraps
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from flask import request, g
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from .extensions import db
from .models import User, Workspace, AuditLog


class APIError(Exception):
    def __init__(self, message, status=400, details=None, code='request_error'):
        self.message, self.status, self.details, self.code = message, status, details, code


def require(*roles):
    """Authenticate and authorize the account selected in the signed session."""
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapped(*args, **kwargs):
            user = db.session.get(User, get_jwt_identity())
            if not user or not user.active or user.token_version != get_jwt().get('ver'):
                raise APIError('Sessão inválida ou revogada.', 401)
            from .access import workspace_role
            workspace_id = get_jwt().get('wid', user.workspace_id)
            workspace = db.session.get(Workspace, workspace_id)
            role = workspace_role(user, workspace)
            if not role:
                raise APIError('Você não tem acesso a esta conta.', 403)
            expected = request.headers.get('X-Workspace-ID')
            if expected and expected != workspace_id:
                raise APIError('A conta foi alterada em outra aba. Recarregue a página.', 409, code='account_changed')
            if roles and role not in roles:
                raise APIError('Você não tem permissão para esta operação.', 403)
            g.user, g.workspace_id, g.role = user, workspace_id, role
            return fn(*args, **kwargs)
        return wrapped
    return decorator


def query(model):
    return model.query.filter_by(workspace_id=g.workspace_id)


def get(model, identifier, lock=False):
    q = query(model).filter_by(id=str(identifier))
    row = (q.with_for_update() if lock else q).first()
    if row is None:
        raise APIError('Registro não encontrado.', 404)
    return row


def payload(schema, partial=False):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError('Envie um objeto JSON válido.')
    result = schema().load(data, partial=partial)
    # SQLAlchemy portable UUIDs are stored as strings.
    import uuid

    def convert(value):
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, list):
            return [convert(item) for item in value]
        return value
    return {key: convert(value) for key, value in result.items()}


def audit(action, row, details=None):
    details = dict(details or {})
    target = row.id if row.__tablename__ == 'workspaces' else getattr(row, 'workspace_id', g.workspace_id)
    if target and target != g.workspace_id:
        details['target_workspace_id'] = target
    db.session.add(AuditLog(workspace_id=g.workspace_id, user_id=g.user.id,
                            action=action, resource=row.__tablename__, resource_id=row.id,
                            details=details or {}))


def add(model, data):
    row = model(workspace_id=g.workspace_id, **data)
    db.session.add(row)
    db.session.flush()
    audit('create', row)
    return row


def update(row, data):
    for key, value in data.items():
        setattr(row, key, value)
    audit('update', row, {'fields': list(data)})


def commit(row, status=200, serializer=None):
    db.session.commit()
    return (serializer(row) if serializer else row.to_dict()), status


def page(q, serializer=None):
    try:
        number = max(1, int(request.args.get('page', 1)))
        size = min(100, max(1, int(request.args.get('per_page', 20))))
    except ValueError:
        raise APIError('Paginação inválida.')
    result = q.paginate(page=number, per_page=size, error_out=False)
    return {'items': [(serializer(x) if serializer else x.to_dict()) for x in result.items],
            'page': number, 'per_page': size, 'total': result.total, 'pages': result.pages}


def date_arg(name, default):
    value = request.args.get(name)
    if value is None:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise APIError(f'Data inválida: {name}. Use AAAA-MM-DD.')


def today():
    workspace = db.session.get(Workspace, g.workspace_id)
    return datetime.now(ZoneInfo(workspace.timezone)).date()


def validate_timezone(value):
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise APIError('Fuso horário inválido.')


def dates_valid(start, end):
    if start and end and end < start:
        raise APIError('A data final deve ser igual ou posterior à inicial.')


def user_ref(identifier):
    if identifier:
        from .access import account_users
        user = next((u for u in account_users(g.workspace_id) if u.id == str(identifier)), None)
        if not user:
            raise APIError('Responsável não encontrado nesta conta.', 404)
        if not user.active:
            raise APIError('O responsável está inativo.')


def money_string(value):
    from decimal import Decimal
    return format(Decimal(value).quantize(Decimal('0.01')), '.2f')
