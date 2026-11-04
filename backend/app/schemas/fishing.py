from marshmallow import fields as f
from marshmallow import validate

from .base import StrictSchema, choice, ref, text


class SettingsSchema(StrictSchema):
    enabled = f.Boolean(required=True)
    brand_name = text(150, required=True)
    brand_profile = text(3000, required=True)
    tone = text(300, required=True)
    examples = f.String(validate=validate.Length(max=2000), load_default='')
    allowed_topics = f.String(validate=validate.Length(max=2000), load_default='')
    forbidden_words = f.List(text(80), validate=validate.Length(max=100), load_default=list)
    blocked_authors = f.List(text(30), validate=validate.Length(max=200), load_default=list)
    own_username = f.String(validate=validate.Regexp(r'^[a-zA-Z0-9_.]{0,30}$'), load_default='')
    objective = choice('seguidores visitas dms', load_default='visitas')
    score_threshold = f.Integer(strict=True, validate=validate.Range(min=1, max=100), load_default=60)
    daily_limit = f.Integer(strict=True, validate=validate.Range(min=1, max=100), load_default=40)
    daily_ai_limit = f.Integer(strict=True, validate=validate.Range(min=1, max=500), load_default=100)


class PostSchema(StrictSchema):
    url = text(500, required=True)
    caption = text(5000, required=True)
    author = f.String(validate=validate.Regexp(r'^@?[a-zA-Z0-9_.]{0,30}$'), load_default='')
    image_data = f.String(validate=validate.Length(max=5600000), allow_none=True, load_default=None)


class OpenSchema(StrictSchema):
    draft_id = ref(required=True)
    text = text(220, required=True)


class DecisionSchema(StrictSchema):
    action = choice('publicado pulado desfazer', required=True)
