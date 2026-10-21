"""Validators shared by user-editable page content (forms and funnel pages)."""

import re
from urllib.parse import urlparse

from marshmallow import ValidationError, validate

HEX_COLOR = validate.Regexp(r'^#[0-9a-fA-F]{6}$', error='Use uma cor no formato #RRGGBB.')
FONTS = ('sans', 'serif', 'mono', 'rounded')
LINK_SCHEMES = ('http', 'https', 'mailto', 'tel')
_ID = re.compile(r'^[A-Za-z0-9_-]{1,40}$')


def valid_url(value, schemes=('http', 'https'), allow_relative=False, max_length=500):
    """Reject javascript:, data: and protocol-relative links; pages render these URLs in href/src."""
    if not isinstance(value, str) or len(value) > max_length or any(ch in value for ch in '\r\n\t '):
        raise ValidationError('Link inválido.')
    if allow_relative and value.startswith('/') and not value.startswith('//'):
        return value
    parsed = urlparse(value)
    if parsed.scheme not in schemes or (parsed.scheme in ('http', 'https') and not parsed.netloc):
        raise ValidationError('Use um link começando com https://.')
    return value


def url_or_empty(schemes=('http', 'https'), allow_relative=False):
    def check(value):
        if value:
            valid_url(value, schemes, allow_relative)

    return check


def valid_id(value):
    if not isinstance(value, str) or not _ID.match(value):
        raise ValidationError('Identificador inválido.')
