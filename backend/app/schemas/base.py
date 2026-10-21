from decimal import Decimal

from marshmallow import RAISE, Schema, validate
from marshmallow import fields as f


def text(length=180, **kw):
    return f.String(
        validate=[validate.Length(min=1, max=length), validate.Regexp(r'\S', error='Informe um texto válido.')], **kw
    )


def choice(options, **kw):
    return f.String(validate=validate.OneOf(options.split()), **kw)


def money(required=False, zero=False):
    return f.Decimal(
        places=2,
        as_string=True,
        required=required,
        allow_nan=False,
        validate=validate.Range(min=Decimal('0') if zero else Decimal('0.01'), max=Decimal('999999999999.99')),
    )


def ref(required=False, nullable=False):
    return f.UUID(required=required, allow_none=nullable)


class StrictSchema(Schema):
    class Meta:
        unknown = RAISE
