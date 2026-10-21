from marshmallow import fields as f
from marshmallow import validate

from .base import StrictSchema, ref


class DomainSchema(StrictSchema):
    hostname = f.String(required=True, validate=validate.Length(min=3, max=253))
    funnel_id = ref(nullable=True)


class DomainUpdateSchema(StrictSchema):
    funnel_id = ref(nullable=True)
