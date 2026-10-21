from decimal import Decimal, InvalidOperation

from marshmallow import fields as f
from marshmallow import validate

from ..schemas import StrictSchema, choice


class PredicateSchema(StrictSchema):
    field = f.String(
        required=True,
        validate=validate.Regexp(
            r'^(source|name|email|phone|tag|deal\.(?:stage_id|status|amount)|comment\.(?:text|media_id)|custom\.[a-z][a-z0-9_]{0,39})$'
        ),
    )
    operator = choice('equals not_equals contains exists gte lt', required=True)
    value = f.String(validate=validate.Length(max=2000), load_default='')


class ConditionsSchema(StrictSchema):
    mode = choice('all any', load_default='all')
    items = f.List(f.Nested(PredicateSchema), validate=validate.Length(max=10), load_default=list)


def matches(conditions, contact, deal=None, context=None):
    results = []
    for item in (conditions or {}).get('items', []):
        key, operator, expected = item['field'], item['operator'], item.get('value', '')
        actual = (
            (context or {}).get(key[8:])
            if key.startswith('comment.')
            else getattr(deal, key[5:], None)
            if key.startswith('deal.')
            else (contact.custom_fields or {}).get(key[7:])
            if key.startswith('custom.')
            else ((contact.tags or []) if key == 'tag' else getattr(contact, key, None))
        )
        if operator == 'exists':
            result = actual is not None and actual != '' and actual != []
        elif operator in ('gte', 'lt'):
            try:
                a, b = Decimal(str(actual)), Decimal(expected)
                result = a.is_finite() and b.is_finite() and (a >= b if operator == 'gte' else a < b)
            except (InvalidOperation, TypeError, ValueError):
                result = False
        elif isinstance(actual, list):
            equal = expected.casefold() in {str(v).casefold() for v in actual}
            result = not equal if operator == 'not_equals' else equal
        else:
            a, b = str(actual or '').casefold(), expected.casefold()
            result = b in a if operator == 'contains' else (a != b if operator == 'not_equals' else a == b)
        results.append(result)
    return not results or (any(results) if conditions.get('mode') == 'any' else all(results))
