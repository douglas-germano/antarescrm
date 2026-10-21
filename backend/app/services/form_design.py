"""Look-and-feel and behaviour settings that form owners can customise per form."""

from marshmallow import fields as f
from marshmallow import validate

from ..schemas.base import StrictSchema
from .safe_values import FONTS, HEX_COLOR, url_or_empty

DEFAULT_DESIGN = {
    'background': '#f2f2f2',
    'card_color': '#ffffff',
    'text_color': '#25282b',
    'font': 'sans',
    'radius': 6,
    'align': 'left',
    'max_width': 520,
    'layout': 'card',
    'button_label': 'Enviar solicitação',
    'button_style': 'pill',
    'button_width': 'auto',
    'logo_url': '',
    'show_brand': True,
}


class DesignSchema(StrictSchema):
    background = f.String(validate=HEX_COLOR)
    card_color = f.String(validate=HEX_COLOR)
    text_color = f.String(validate=HEX_COLOR)
    font = f.String(validate=validate.OneOf(FONTS))
    radius = f.Integer(validate=validate.Range(min=0, max=32))
    align = f.String(validate=validate.OneOf(['left', 'center']))
    max_width = f.Integer(validate=validate.Range(min=320, max=960))
    layout = f.String(validate=validate.OneOf(['card', 'plain']))
    button_label = f.String(validate=validate.Length(min=1, max=60))
    button_style = f.String(validate=validate.OneOf(['pill', 'rounded', 'square']))
    button_width = f.String(validate=validate.OneOf(['auto', 'full']))
    logo_url = f.String(validate=url_or_empty())
    show_brand = f.Boolean()


class BaseFieldSchema(StrictSchema):
    label = f.String(validate=validate.Length(min=1, max=120))
    placeholder = f.String(validate=validate.Length(max=120))
    visible = f.Boolean()
    required = f.Boolean()


class BaseFieldsSchema(StrictSchema):
    name = f.Nested(BaseFieldSchema)
    email = f.Nested(BaseFieldSchema)
    phone = f.Nested(BaseFieldSchema)


class AfterSubmitSchema(StrictSchema):
    type = f.String(validate=validate.OneOf(['message', 'redirect']), load_default='message')
    url = f.String(validate=url_or_empty(), load_default='')


class SettingsSchema(StrictSchema):
    consent_text = f.String(validate=validate.Length(min=1, max=255))
    base_fields = f.Nested(BaseFieldsSchema)
    after_submit = f.Nested(AfterSubmitSchema)


def merged_design(stored):
    return {**DEFAULT_DESIGN, **(stored or {})}


def phone_required(settings):
    return bool(((settings or {}).get('base_fields') or {}).get('phone', {}).get('required'))


def validate_settings(settings):
    """A redirect needs a destination; the rest is covered by the schema."""
    from ..common import APIError

    after = (settings or {}).get('after_submit') or {}
    if after.get('type') == 'redirect' and not after.get('url'):
        raise APIError('Informe o link de redirecionamento.', 422)
