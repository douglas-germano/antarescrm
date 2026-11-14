from decimal import Decimal, InvalidOperation

from marshmallow import fields as f
from marshmallow import validate

from ..schemas import StrictSchema, choice


class PredicateSchema(StrictSchema):
    field = f.String(
        required=True,
        validate=validate.Regexp(
            r'^(source|name|email|phone|tag|deal\.(?:stage_id|status|amount)|comment\.(?:text|media_id)|reply\.text|task\.title|custom\.[a-z][a-z0-9_]{0,39})$'
        ),
    )
    operator = choice('equals not_equals contains exists gte lt', required=True)
    value = f.String(validate=validate.Length(max=2000), load_default='')


class ConditionsSchema(StrictSchema):
    mode = choice('all any', load_default='all')
    items = f.List(f.Nested(PredicateSchema), validate=validate.Length(max=10), load_default=list)


def actual_value(key, contact, deal=None, context=None):
    return (
        (context or {}).get(key[8:])
        if key.startswith('comment.')
        else (context or {}).get('task_title')
        if key == 'task.title'
        else (context or {}).get('reply_text')
        if key == 'reply.text'
        else getattr(deal, key[5:], None)
        if key.startswith('deal.')
        else (contact.custom_fields or {}).get(key[7:])
        if key.startswith('custom.')
        else ((contact.tags or []) if key == 'tag' else getattr(contact, key, None))
    )


def check(item, contact, deal=None, context=None):
    key, operator, expected = item['field'], item['operator'], item.get('value', '')
    actual = actual_value(key, contact, deal, context)
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
    return result, actual


def explain(conditions, contact, deal=None, context=None):
    """Each predicate with the value it saw, so a test shows why a condition passed or failed."""
    items = []
    for item in (conditions or {}).get('items', []):
        passed, actual = check(item, contact, deal, context)
        if isinstance(actual, Decimal):
            actual = format(actual, '.2f')
        elif actual is not None and not isinstance(actual, (str, int, float, bool, list)):
            actual = str(actual)
        items.append(
            {
                'field': item['field'],
                'operator': item['operator'],
                'value': item.get('value', ''),
                'actual': actual,
                'passed': passed,
            }
        )
    return items


def matches(conditions, contact, deal=None, context=None):
    results = [check(item, contact, deal, context)[0] for item in (conditions or {}).get('items', [])]
    return not results or (any(results) if conditions.get('mode') == 'any' else all(results))
