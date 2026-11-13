from flask import Flask

from app.error_reporting import _scrub_event, init_error_reporting


def test_disabled_without_dsn(monkeypatch):
    app = Flask('t')
    monkeypatch.delenv('SENTRY_DSN', raising=False)
    assert init_error_reporting(app) is False


def test_disabled_in_testing_even_with_dsn(monkeypatch):
    app = Flask('t')
    app.testing = True
    monkeypatch.setenv('SENTRY_DSN', 'https://key@example.ingest.sentry.io/1')
    assert init_error_reporting(app) is False


def test_scrub_removes_customer_data():
    event = {
        'request': {
            'method': 'POST',
            'url': 'https://x/api/v1/contacts?phone=5565999999999',
            'data': {'message': 'olá'},
            'headers': {'Authorization': 'Bearer secret'},
            'cookies': {'a': 'b'},
        },
        'user': {'email': 'a@b.com'},
        'breadcrumbs': [{'message': 'x'}],
        'exception': {
            'values': [
                {
                    'type': 'ValueError',
                    'value': 'token=abc',
                    'stacktrace': {'frames': [{'function': 'f', 'vars': {'token': 'abc'}}]},
                }
            ]
        },
    }
    result = _scrub_event(event, {})
    assert result['request'] == {'method': 'POST', 'url': 'https://x/api/v1/contacts'}
    assert 'user' not in result and 'breadcrumbs' not in result
    value = result['exception']['values'][0]
    assert value['value'] == '' and value['type'] == 'ValueError'
    assert 'vars' not in value['stacktrace']['frames'][0]
