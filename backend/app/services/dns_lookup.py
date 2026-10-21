"""DNS lookups through a DNS-over-HTTPS resolver, so no resolver library has to be installed on the server."""

import requests
from flask import current_app

TYPES = {'A': 1, 'CNAME': 5, 'TXT': 16}


class DNSLookupError(Exception):
    """The resolver could not be reached or answered with an error; says nothing about the record itself."""


def dns_query(name, rtype):
    """Return the record values for `name`; an absent record is an empty list."""
    try:
        response = requests.get(
            current_app.config['DNS_RESOLVER_URL'],
            params={'name': name, 'type': rtype},
            headers={'Accept': 'application/dns-json'},
            timeout=5,
        )
        response.raise_for_status()
        body = response.json()
    except (requests.RequestException, ValueError) as error:
        raise DNSLookupError(type(error).__name__) from None
    if body.get('Status') not in (0, 3):  # 0 = ok, 3 = name does not exist
        raise DNSLookupError('status ' + str(body.get('Status')))
    values = []
    for answer in body.get('Answer') or []:
        if answer.get('type') != TYPES[rtype]:
            continue
        data = str(answer.get('data', '')).strip()
        values.append(data.replace('" "', '').strip('"') if rtype == 'TXT' else data.rstrip('.').lower())
    return values
