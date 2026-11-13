"""Optional Sentry error reporting. Disabled unless SENTRY_DSN is set.

Follows the same rule as observability.py: no request bodies, query strings, cookies,
headers or exception messages leave the process, since they can carry customer data
(phone numbers, message text) or provider tokens.
"""

import os

SAFE_REQUEST_KEYS = {'method', 'url'}


def _scrub_event(event, hint):
    request = event.get('request')
    if isinstance(request, dict):
        url = str(request.get('url') or '').split('?', 1)[0]
        event['request'] = {'method': request.get('method'), 'url': url}
    event.pop('user', None)
    event.pop('breadcrumbs', None)
    event.pop('extra', None)
    for entry in (event.get('exception') or {}).get('values', []):
        # Exception messages may embed provider URLs, tokens or user data.
        entry['value'] = ''
        for frame in (entry.get('stacktrace') or {}).get('frames', []):
            frame.pop('vars', None)
    event.pop('logentry', None)
    return event


def init_error_reporting(app):
    dsn = os.getenv('SENTRY_DSN')
    if not dsn or app.testing:
        return False
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv('APP_ENV', 'development'),
        release=os.getenv('APP_RELEASE') or None,
        integrations=[FlaskIntegration()],
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size='never',
        max_breadcrumbs=0,
        traces_sample_rate=float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0')),
        before_send=_scrub_event,
    )
    return True
