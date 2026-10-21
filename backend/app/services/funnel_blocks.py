"""Validation of funnel page blocks. Pages are stored as data and rendered by the client as plain React nodes,
so every URL and enum is checked here and unknown properties are rejected."""

import re
from datetime import datetime
from urllib.parse import urlparse

from marshmallow import ValidationError

from ..common import APIError
from .safe_values import FONTS, LINK_SCHEMES, valid_id, valid_url

HEX = re.compile(r'^#[0-9a-fA-F]{6}$')
MAX_BLOCKS = 80
ALIGN = ('left', 'center', 'right')
PADDING = ('none', 'sm', 'md', 'lg')
WIDTH = ('narrow', 'normal', 'wide')
VIDEO_HOSTS = ('youtube.com', 'www.youtube.com', 'youtu.be', 'player.vimeo.com', 'vimeo.com', 'www.vimeo.com')


def _text(limit, required=False):
    def check(value):
        if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
            raise ValidationError('Texto inválido.')
        return value

    return check


def _enum(*options):
    def check(value):
        if value not in options:
            raise ValidationError('Opção inválida.')
        return value

    return check


def _url(schemes=('http', 'https'), allow_empty=True):
    def check(value):
        if value == '' and allow_empty:
            return value
        return valid_url(value, schemes)

    return check


def _video(value):
    if value == '':
        return value
    valid_url(value)
    if (urlparse(value).hostname or '') not in VIDEO_HOSTS:
        raise ValidationError('Use um vídeo do YouTube ou do Vimeo.')
    return value


def _color(value):
    if value != '' and not (isinstance(value, str) and HEX.fullmatch(value)):
        raise ValidationError('Cor inválida.')
    return value


def _bool(value):
    if not isinstance(value, bool):
        raise ValidationError('Valor inválido.')
    return value


def _number(low, high):
    def check(value):
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValidationError('Número fora do intervalo.')
        return value

    return check


def _strings(limit, max_items):
    def check(value):
        if not isinstance(value, list) or len(value) > max_items:
            raise ValidationError('Lista inválida.')
        return [_text(limit)(item) for item in value]

    return check


def _pairs(max_items):
    def check(value):
        if not isinstance(value, list) or len(value) > max_items:
            raise ValidationError('Lista inválida.')
        result = []
        for item in value:
            if not isinstance(item, dict) or set(item) - {'q', 'a'}:
                raise ValidationError('Item inválido.')
            result.append({'q': _text(200)(item.get('q', '')), 'a': _text(1500)(item.get('a', ''))})
        return result

    return check


def _datetime(value):
    if value == '':
        return value
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        raise ValidationError('Data inválida.') from None
    return value


def _form_id(value):
    if value == '':
        return value
    if not isinstance(value, str) or len(value) != 36:
        raise ValidationError('Formulário inválido.')
    return value


LINK = _url(LINK_SCHEMES)
IMAGE = _url()

# type -> {property: validator}; every property is optional and defaults on the client.
BLOCKS = {
    'heading': {'text': _text(200), 'level': _enum(1, 2, 3)},
    'text': {'text': _text(5000), 'size': _enum('sm', 'md', 'lg')},
    'image': {'src': IMAGE, 'alt': _text(200), 'link': LINK, 'rounded': _bool},
    'video': {'url': _video},
    'button': {
        'label': _text(80),
        'action': _enum('next', 'url'),
        'url': LINK,
        'variant': _enum('primary', 'secondary'),
        'full_width': _bool,
    },
    'form': {'form_id': _form_id, 'on_submit': _enum('next', 'message', 'url'), 'url': LINK},
    'list': {'items': _strings(200, 20), 'icon': _enum('check', 'dot')},
    'testimonial': {'quote': _text(500), 'author': _text(100), 'role': _text(100), 'avatar': IMAGE},
    'faq': {'items': _pairs(15)},
    'countdown': {
        'mode': _enum('fixed', 'evergreen'),
        'target': _datetime,
        'minutes': _number(1, 10080),
        'expired_text': _text(200),
    },
    'divider': {},
    'spacer': {'height': _number(8, 160)},
}
STYLE = {
    'align': _enum(*ALIGN),
    'background': _color,
    'color': _color,
    'padding': _enum(*PADDING),
    'width': _enum(*WIDTH),
}
STEP_SETTINGS = {
    'title': _text(120),
    'description': _text(300),
    'background': _color,
    'width': _enum(*WIDTH),
}
THEME = {
    'accent_color': _color,
    'background': _color,
    'text_color': _color,
    'font': _enum(*FONTS),
    'radius': _number(0, 32),
}


def _apply(spec, data, label):
    if not isinstance(data, dict):
        raise APIError(f'{label}: formato inválido.', 422)
    unknown = set(data) - set(spec)
    if unknown:
        raise APIError(f'{label}: propriedade não permitida ({", ".join(sorted(unknown))}).', 422)
    clean = {}
    for key, value in data.items():
        try:
            clean[key] = spec[key](value)
        except (ValidationError, TypeError, ValueError):
            raise APIError(f'{label}: valor inválido em "{key}".', 422) from None
    return clean


def clean_theme(theme):
    return _apply(THEME, theme, 'Tema')


def clean_settings(settings):
    return _apply(STEP_SETTINGS, settings, 'Configurações da página')


def clean_blocks(blocks):
    if not isinstance(blocks, list) or len(blocks) > MAX_BLOCKS:
        raise APIError(f'Uma página aceita até {MAX_BLOCKS} blocos.', 422)
    seen, result = set(), []
    for index, block in enumerate(blocks, 1):
        label = f'Bloco {index}'
        if not isinstance(block, dict) or set(block) - {'id', 'type', 'props', 'style'}:
            raise APIError(f'{label}: formato inválido.', 422)
        try:
            valid_id(block.get('id'))
        except ValidationError:
            raise APIError(f'{label}: identificador inválido.', 422) from None
        if block['id'] in seen:
            raise APIError(f'{label}: identificador repetido.', 422)
        seen.add(block['id'])
        spec = BLOCKS.get(block.get('type'))
        if spec is None:
            raise APIError(f'{label}: tipo de bloco desconhecido.', 422)
        result.append(
            {
                'id': block['id'],
                'type': block['type'],
                'props': _apply(spec, block.get('props', {}), label),
                'style': _apply(STYLE, block.get('style', {}), label),
            }
        )
    return result


def form_ids(blocks):
    return [b['props']['form_id'] for b in blocks if b['type'] == 'form' and b['props'].get('form_id')]
