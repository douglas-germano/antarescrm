from marshmallow import fields as f
from marshmallow import validate

from .base import StrictSchema, choice, text

STEP_KINDS = 'landing optin sales upsell thankyou custom'
TEMPLATES = 'blank lead_magnet sales'


class FunnelSchema(StrictSchema):
    name = text(150, required=True)
    description = f.String(validate=validate.Length(max=1000))
    status = choice('draft published')
    theme = f.Dict(keys=f.String(), values=f.Raw())
    template = choice(TEMPLATES, load_default='blank')


class StepSchema(StrictSchema):
    name = text(150, required=True)
    slug = f.String(validate=[validate.Length(min=1, max=60), validate.Regexp(r'^[a-z0-9]+(-[a-z0-9]+)*$')])
    kind = choice(STEP_KINDS)
    blocks = f.List(f.Dict(), validate=validate.Length(max=80))
    settings = f.Dict(keys=f.String(), values=f.Raw())


class ReorderSchema(StrictSchema):
    order = f.List(f.UUID(), required=True, validate=validate.Length(min=1, max=50))


class ViewSchema(StrictSchema):
    visitor_id = f.UUID(required=True)
