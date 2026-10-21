"""
Shared parsing helpers for raw Evolution API / Baileys WhatsApp message objects.

Used both by the live webhook handler (routes/webhook.py, one message at a
time as events arrive) and by the historical sync path
(services/evolution_service.py, bulk messages fetched from
chat/findMessages), so both stay in sync on what counts as a "message with
content" and how media/timestamps are read.
"""

from datetime import datetime, timezone

from app.models import now as utcnow


def utcfromtimestamp(value):
    return datetime.fromtimestamp(value, timezone.utc)


MEDIA_MESSAGE_KEYS = {
    'imageMessage': 'image',
    'audioMessage': 'audio',
    'documentMessage': 'document',
    'documentWithCaptionMessage': 'document',
    'stickerMessage': 'sticker',
    'videoMessage': 'video',
    'ptvMessage': 'video',
}

MEDIA_PLACEHOLDER_TEXT = {
    'image': 'Imagem enviada',
    'audio': 'Audio enviado',
    'document': 'Documento enviado',
    'sticker': 'Figurinha enviada',
    'video': 'Vídeo enviado',
}


def _sanitize_media_url(url: str | None) -> str | None:
    """
    Only allow http(s) media URLs through. The frontend renders media_url
    directly as an <img src>/<audio src>/download <a href> - without this,
    a crafted Evolution API payload (e.g. a compromised/malicious gateway)
    could plant a `javascript:` URI that runs when a staff member clicks it.
    """
    if not url or not isinstance(url, str):
        return None
    if not url.lower().startswith(('http://', 'https://')):
        return None
    return url


MESSAGE_WRAPPERS = (
    'ephemeralMessage',
    'viewOnceMessage',
    'viewOnceMessageV2',
    'viewOnceMessageV2Extension',
    'documentWithCaptionMessage',
)


def unwrap_message(message_obj: dict) -> dict:
    """Unwrap Baileys containers without following quoted messages."""
    current = message_obj if isinstance(message_obj, dict) else {}
    for _ in range(8):
        nested = next(
            (
                current[key].get('message')
                for key in MESSAGE_WRAPPERS
                if isinstance(current.get(key), dict) and isinstance(current[key].get('message'), dict)
            ),
            None,
        )
        if nested is None:
            break
        current = nested
    return current


def extract_media(message_obj: dict) -> tuple | None:
    """Return (message_type, media_url, mimetype, caption) for the first media key found, or None."""
    message_obj = unwrap_message(message_obj)
    for key, media_type in MEDIA_MESSAGE_KEYS.items():
        media = message_obj.get(key)
        if not isinstance(media, dict) or not media:
            continue
        # documentWithCaptionMessage nests the real document payload one
        # level deeper: {"message": {"documentMessage": {...}}}
        if key == 'documentWithCaptionMessage':
            media = media.get('message', {}).get('documentMessage', media)
        url = _sanitize_media_url(media.get('url') or media.get('directPath'))
        mimetype = media.get('mimetype') or media.get('mimeType')
        caption = media.get('caption', '')
        return media_type, url, mimetype, caption
    return None


def extract_text(message_obj: dict) -> str:
    """Return the plain text content of a message object, or '' if none."""
    message_obj = unwrap_message(message_obj)
    text = message_obj.get('conversation')
    extended = message_obj.get('extendedTextMessage')
    if not text and isinstance(extended, dict):
        text = extended.get('text')
    return text if isinstance(text, str) else ''


def parse_message_timestamp(raw_ts) -> datetime:
    """
    Parse a Baileys/Evolution `messageTimestamp` value into a naive UTC
    datetime. Historically this field has shown up as a unix-seconds int, a
    numeric string, or a Long.js-style `{"low": ..., "high": ..., "unsigned":
    ...}` object depending on the Evolution API version - handle all three
    defensively rather than assuming one shape.
    """
    try:
        if isinstance(raw_ts, dict):
            seconds = int(raw_ts.get('low', 0))
        else:
            seconds = int(raw_ts)
        return utcfromtimestamp(seconds)
    except (TypeError, ValueError, OSError, OverflowError):
        return utcnow()


def normalize_raw_message(raw: dict) -> dict | None:
    """
    Normalize one raw Evolution/Baileys message object (as found in a
    `messages.upsert` webhook payload's `data`, or a `chat/findMessages`
    record) into a plain dict:

        {evolution_id, from_me, phone, timestamp, content, message_type,
         media_url, media_mimetype, caption}

    Returns None for group messages or messages with no usable content
    (neither text nor a recognized media type).
    """
    if not isinstance(raw, dict):
        return None
    key = raw.get('key', {}) or {}
    if not isinstance(key, dict):
        return None
    remote_jid = key.get('remoteJid', '') or ''

    if remote_jid.endswith('@lid'):
        remote_jid = key.get('remoteJidAlt') or raw.get('remoteJidAlt') or ''
    if not remote_jid or not remote_jid.endswith('@s.whatsapp.net'):
        return None

    message_obj = raw.get('message', {}) or {}
    if not isinstance(message_obj, dict):
        return None
    text = extract_text(message_obj)
    media = None if text else extract_media(message_obj)

    if not text and not media:
        return None

    result = {
        'evolution_id': key.get('id'),
        'from_me': bool(key.get('fromMe', False)),
        'phone': remote_jid.split('@')[0] if remote_jid else None,
        'timestamp': parse_message_timestamp(raw.get('messageTimestamp')),
    }

    if media:
        message_type, media_url, mimetype, caption = media
        result.update(
            {
                'content': caption or MEDIA_PLACEHOLDER_TEXT.get(message_type, 'Midia enviada'),
                'message_type': message_type,
                'media_url': media_url,
                'media_mimetype': mimetype,
                'caption': caption or None,
            }
        )
    else:
        result.update(
            {
                'content': text,
                'message_type': 'text',
                'media_url': None,
                'media_mimetype': None,
                'caption': None,
            }
        )

    return result
