"""Decode and transcribe inbound Atlas audio inside the worker."""

from functools import lru_cache
from io import BytesIO
from time import monotonic
from urllib.parse import urlsplit

import requests

from ..common import APIError
from ..models import InboxMessage, InstagramEvent, WhatsAppMessage
from . import whatsapp

INSTAGRAM_AUDIO = '[Áudio recebido no Instagram]'
MAX_BYTES = 10 * 1024 * 1024
RATE = 16000
MAX_SAMPLES = 90 * RATE


def instagram_audio_url(message):
    for attachment in message.get('attachments') or []:
        if isinstance(attachment, dict) and attachment.get('type') == 'audio':
            payload = attachment.get('payload')
            if isinstance(payload, dict) and isinstance(payload.get('url'), str):
                return payload['url']
    return None


def instagram_audio(workspace_id, message_id):
    row = InboxMessage.query.filter_by(workspace_id=workspace_id, id=message_id, direction='in').one()
    event = InstagramEvent.query.filter_by(
        workspace_id=workspace_id, event_key=row.idempotency_key.removeprefix('instagram:'), kind='messaging'
    ).first()
    url = instagram_audio_url(event.payload.get('message', {})) if event else None
    try:
        parsed = urlsplit(url or '')
        host = parsed.hostname or ''
        if (
            parsed.scheme != 'https'
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
            or not any(host == domain or host.endswith('.' + domain) for domain in ('fbcdn.net', 'cdninstagram.com'))
        ):
            raise ValueError
        with requests.get(url, timeout=(3, 8), stream=True, allow_redirects=False) as response:
            if response.status_code != 200:
                raise ValueError
            data = bytearray()
            deadline = monotonic() + 20
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data) > MAX_BYTES or monotonic() > deadline:
                    raise ValueError
            return bytes(data)
    except (requests.RequestException, ValueError):
        raise APIError('O áudio do Instagram não está disponível.', 422) from None


@lru_cache(maxsize=1)
def model():
    from faster_whisper import WhisperModel

    return WhisperModel('/opt/atlas-whisper', device='cpu', compute_type='int8', cpu_threads=2, local_files_only=True)


def transcribe(audio):
    import av
    import numpy as np

    chunks = []
    count = 0
    try:
        if audio.startswith(b'OggS'):
            container_format = 'ogg'
        elif audio[4:8] == b'ftyp':
            container_format = 'mov'
        elif audio.startswith(b'RIFF') and audio[8:12] == b'WAVE':
            container_format = 'wav'
        elif audio.startswith(b'ID3') or (len(audio) >= 2 and audio[0] == 255 and audio[1] & 224 == 224):
            container_format = 'mp3'
        elif audio.startswith(b'\x1a\x45\xdf\xa3'):
            container_format = 'matroska'
        else:
            raise ValueError
        with av.open(
            BytesIO(audio), mode='r', format=container_format, options={'protocol_whitelist': 'pipe'}
        ) as container:
            resampler = av.AudioResampler(format='s16', layout='mono', rate=RATE)
            for frame in container.decode(audio=0):
                for sample in resampler.resample(frame):
                    count += sample.samples
                    if count > MAX_SAMPLES:
                        raise APIError('O Atlas aceita áudios de até 90 segundos.', 422)
                    chunks.append(sample.to_ndarray().ravel())
        if not chunks:
            raise ValueError
        samples = np.concatenate(chunks).astype(np.float32) / 32768
        segments, _ = model().transcribe(samples, beam_size=1, vad_filter=True, condition_on_previous_text=False)
        transcript = ' '.join(segment.text.strip() for segment in segments).strip()
        if not transcript:
            raise ValueError
        return transcript[:2000]
    except (av.error.FFmpegError, ValueError, IndexError, RuntimeError):
        raise APIError('Não foi possível transcrever o áudio.', 422) from None


def apply(workspace_id, job):
    sources = job.pop('_audio', [])
    deadline = monotonic() + 90
    for source in sources:
        if monotonic() > deadline:
            raise APIError('O lote de áudio excedeu o tempo de processamento.', 422)
        if source['channel'] == 'whatsapp':
            message = WhatsAppMessage.query.filter_by(
                workspace_id=workspace_id, id=source['id'], direction='in', kind='audio'
            ).one()
            data = whatsapp.media_for(whatsapp.connection_for(workspace_id), message).content
        else:
            data = instagram_audio(workspace_id, source['id'])
        transcript = transcribe(data)
        job['novas_mensagens'][source['index']] = transcript
        if source['latest']:
            job['mensagem_recebida'] = transcript
