"""Server-authoritative form definitions, visibility and typed answers."""
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from marshmallow import fields as f, validate, validates_schema, ValidationError
from ..schemas import StrictSchema, text, choice
from ..common import APIError


class VisibilitySchema(StrictSchema):
    field = f.String(required=True, validate=validate.Regexp(r'^[a-z][a-z0-9_]{0,39}$'))
    equals = f.Raw(required=True)


class FormFieldSchema(StrictSchema):
    key = f.String(required=True, validate=validate.Regexp(r'^[a-z][a-z0-9_]{0,39}$'))
    label = text(120, required=True)
    type = choice('text textarea number date select checkbox', required=True)
    required = f.Boolean(load_default=False)
    options = f.List(text(120), validate=validate.Length(max=50), load_default=list)
    map_to = f.String(validate=validate.Regexp(r'^[a-z][a-z0-9_]{0,39}$'), allow_none=True)
    show_if = f.Nested(VisibilitySchema, allow_none=True)


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
        if mapping: mappings.add(mapping)
        if item['type'] == 'select' and (not item['options'] or len(set(item['options'])) != len(item['options'])):
            raise APIError('Informe opções únicas para os campos de seleção.', 422)


def parse_answers(definitions, supplied):
    if set(supplied) - {item['key'] for item in definitions}:
        raise APIError('O formulário mudou. Recarregue a página antes de enviar.', 422)
    answers, mapped = {}, {}
    for item in definitions:
        key = item['key']
        condition = item.get('show_if')
        if condition and answers.get(condition['field']) != condition['equals']:
            continue
        value = supplied.get(key)
        if value is None or value == '' or (item['type'] == 'checkbox' and value is False):
            if item['required']: raise APIError('Preencha o campo: ' + item['label'], 422)
            if item['type'] != 'checkbox': continue
            value = False
        kind = item['type']
        valid = True
        if kind == 'checkbox':
            valid = isinstance(value, bool)
        elif kind == 'number':
            try:
                if isinstance(value, bool): raise ValueError()
                number = Decimal(str(value))
                valid = number.is_finite() and abs(number) <= Decimal('999999999999.99')
                value = str(number)
            except (InvalidOperation, ValueError): valid = False
        elif kind == 'date':
            try: value = date.fromisoformat(value).isoformat()
            except (ValueError, TypeError): valid = False
        else:
            valid = isinstance(value, str) and len(value) <= 2000
            if valid:
                value = value.strip()
                valid = bool(value) or not item['required']
            if valid and kind == 'select': valid = value in item['options']
        if not valid: raise APIError('Confira o campo: ' + item['label'], 422)
        answers[key] = value
        if item.get('map_to'):
            mapped[item['map_to']] = str(value).lower() if isinstance(value, bool) else str(value)
    return answers, mapped
