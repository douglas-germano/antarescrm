"""Server-authoritative form definitions, visibility and typed answers."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from marshmallow import ValidationError, fields, validate
from marshmallow import fields as f

from ..common import APIError
from ..schemas import StrictSchema, choice, text
from .safe_values import valid_url


class VisibilitySchema(StrictSchema):
    field = f.String(required=True, validate=validate.Regexp(r'^[a-z][a-z0-9_]{0,39}$'))
    equals = f.Raw(required=True)


class FormFieldSchema(StrictSchema):
    key = f.String(required=True, validate=validate.Regexp(r'^[a-z][a-z0-9_]{0,39}$'))
    label = text(120, required=True)
    type = choice(
        'text textarea number date select checkbox email phone url radio multiselect heading paragraph divider',
        required=True,
    )
    required = f.Boolean(load_default=False)
    placeholder = f.String(validate=validate.Length(max=120), load_default='')
    help_text = f.String(validate=validate.Length(max=300), load_default='')
    width = f.String(validate=validate.OneOf(['full', 'half']), load_default='full')
    options = f.List(text(120), validate=validate.Length(max=50), load_default=list)
    map_to = f.String(validate=validate.Regexp(r'^[a-z][a-z0-9_]{0,39}$'), allow_none=True)
    show_if = f.Nested(VisibilitySchema, allow_none=True)


CHOICE_TYPES = ('select', 'radio', 'multiselect')
LAYOUT_TYPES = ('heading', 'paragraph', 'divider')


def validate_definitions(definitions):
    keys, mappings = set(), set()
    for item in definitions:
        key = item['key']
        if key in keys or key in {'name', 'email', 'phone', 'consent', 'website'}:
            raise APIError('Use identificadores únicos para os campos adicionais.', 422)
        condition = item.get('show_if')
        if condition and condition['field'] not in keys:
            raise APIError('A condição precisa apontar para um campo anterior.', 422)
        keys.add(key)
        mapping = item.get('map_to')
        if mapping and mapping in mappings:
            raise APIError('Cada campo do CRM pode receber apenas uma resposta.', 422)
        if mapping:
            mappings.add(mapping)
        if item['type'] in CHOICE_TYPES and (not item['options'] or len(set(item['options'])) != len(item['options'])):
            raise APIError('Informe opções únicas para os campos de seleção.', 422)


def _number(value):
    if isinstance(value, bool):
        raise ValueError()
    number = Decimal(str(value))
    if not (number.is_finite() and abs(number) <= Decimal('999999999999.99')):
        raise ValueError()
    return str(number)


def _text(item, value):
    if not isinstance(value, str) or len(value) > 2000:
        raise ValueError()
    value = value.strip()
    kind = item['type']
    if kind == 'email':
        fields.Email().deserialize(value)
        value = value.lower()
    elif kind == 'url':
        valid_url(value)
    elif kind == 'phone' and not re.fullmatch(r'[0-9+()\-.\s]{6,30}', value):
        raise ValueError()
    if kind in ('select', 'radio') and value not in item['options']:
        raise ValueError()
    if not value and item['required']:
        raise ValueError()
    return value


def _clean(item, value):
    """Return the validated, normalised answer or raise ValueError/ValidationError."""
    kind = item['type']
    if kind == 'checkbox':
        if not isinstance(value, bool):
            raise ValueError()
        return value
    if kind == 'number':
        return _number(value)
    if kind == 'date':
        return date.fromisoformat(value).isoformat()
    if kind == 'multiselect':
        if not isinstance(value, list) or len(set(value)) != len(value) or not set(value) <= set(item['options']):
            raise ValueError()
        return value
    return _text(item, value)


def _is_blank(item, value):
    if value is None or value == '' or value == []:
        return True
    return item['type'] == 'checkbox' and value is False


def parse_answers(definitions, supplied):
    answerable = [item for item in definitions if item['type'] not in LAYOUT_TYPES]
    if set(supplied) - {item['key'] for item in answerable}:
        raise APIError('O formulário mudou. Recarregue a página antes de enviar.', 422)
    answers, mapped = {}, {}
    for item in answerable:
        key = item['key']
        condition = item.get('show_if')
        if condition and answers.get(condition['field']) != condition['equals']:
            continue
        value = supplied.get(key)
        if _is_blank(item, value):
            if item['required']:
                raise APIError('Preencha o campo: ' + item['label'], 422)
            if item['type'] != 'checkbox':
                continue
            value = False
        try:
            value = _clean(item, value)
        except (ValueError, TypeError, InvalidOperation, ValidationError):
            raise APIError('Confira o campo: ' + item['label'], 422) from None
        answers[key] = value
        if item.get('map_to'):
            mapped[item['map_to']] = _as_text(value)
    return answers, mapped


def _as_text(value):
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        return ', '.join(value)
    return str(value)
