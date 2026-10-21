import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.types import DateTime, TypeDecorator

from ..extensions import db


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Return aware UTC timestamps on both PostgreSQL and SQLite test stores."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).astimezone(timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).astimezone(timezone.utc)
        return value


class Base(db.Model):
    __abstract__ = True
    id = db.Column(db.String(36), primary_key=True, default=uid)
    created_at = db.Column(UTCDateTime(), default=now, nullable=False)
    updated_at = db.Column(UTCDateTime(), default=now, onupdate=now, nullable=False)

    def to_dict(self):
        result = {}
        for column in self.__table__.columns:
            if column.name in ('password_hash', 'token_version'):
                continue
            value = getattr(self, column.name)
            if isinstance(value, Decimal):
                value = format(value, '.2f')
            elif hasattr(value, 'isoformat'):
                value = value.isoformat()
            result[column.name] = value
        return result


class TenantBase(Base):
    __abstract__ = True
    workspace_id = db.Column(db.String(36), db.ForeignKey('workspaces.id'), nullable=False, index=True)
