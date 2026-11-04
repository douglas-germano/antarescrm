"""Structured, correlated logs without request bodies, query strings or credentials."""

import json
import logging
import re
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, g, has_request_context, request
from flask.logging import default_handler, wsgi_errors_stream

CONTEXT_FIELDS = {
    'request_id',
    'workspace_id',
    'user_id',
    'channel',
    'operation',
    'resource_id',
    'stage',
    'error_type',
    'duration_ms',
    'status',
    'method',
    'endpoint',
}


class StructuredFormatter(logging.Formatter):
    def format(self, record):
        result = {
            'timestamp': datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            'level': record.levelname,
            'event': record.getMessage(),
        }
        result.update(getattr(record, 'event_fields', {}))
        if has_request_context():
            result.setdefault('request_id', getattr(g, 'request_id', None))
            result.setdefault('workspace_id', getattr(g, 'workspace_id', None))
        if record.exc_info:
            result['error_type'] = record.exc_info[0].__name__
            # Exception messages can contain provider URLs, tokens or user data. Retain locations only.
            result['stack'] = [
                {'file': Path(frame.filename).name, 'line': frame.lineno, 'function': frame.name}
                for frame in traceback.extract_tb(record.exc_info[2])
            ]
        return json.dumps(result, ensure_ascii=False, default=str)


def event(name, *, level=logging.INFO, **fields):
    safe = {key: value for key, value in fields.items() if key in CONTEXT_FIELDS}
    if has_request_context():
        safe.setdefault('request_id', getattr(g, 'request_id', None))
        safe.setdefault('workspace_id', getattr(g, 'workspace_id', None))
    current_app.logger.log(level, name, extra={'event_fields': safe})


def register_observability(app):
    app.logger.setLevel(app.config.get('LOG_LEVEL', 'INFO'))
    app.logger.removeHandler(default_handler)
    if not any(getattr(handler, 'antares_structured', False) for handler in app.logger.handlers):
        handler = logging.StreamHandler(wsgi_errors_stream)
        handler.antares_structured = True
        handler.setFormatter(StructuredFormatter())
        app.logger.addHandler(handler)

    @app.before_request
    def start_request():
        supplied = request.headers.get('X-Request-ID', '')
        g.request_id = supplied if re.fullmatch(r'[A-Za-z0-9._-]{1,64}', supplied) else uuid.uuid4().hex
        g.request_started = time.perf_counter()

    @app.after_request
    def finish_request(response):
        response.headers['X-Request-ID'] = g.request_id
        if request.endpoint != 'health' or response.status_code >= 400:
            event(
                'http_request_completed',
                method=request.method,
                endpoint=request.endpoint,
                status=response.status_code,
                duration_ms=round((time.perf_counter() - g.request_started) * 1000, 2),
            )
        return response
