"""Instagram publishing: uploaded media, posts and the container → publish state machine.

Instagram publishes in two steps: a media container is created from a public URL, then published.
Containers are harmless if repeated (they expire unused), so they are created freely. The publish call is
not: the post is marked `publishing` and committed before it, and an ambiguous outcome becomes `unknown`
and is never retried automatically (same rule as direct messages).
"""

import re
import secrets
import uuid
from datetime import timedelta
from urllib.parse import urlparse

from flask import current_app

from ...common import APIError
from ...extensions import db
from ...models import InstagramConnection, InstagramMedia, InstagramPost, now
from ..projects import delete_bytes, storage_path
from . import client, connections

MEDIA_TYPES = ('IMAGE', 'CAROUSEL', 'REELS')
PENDING = ('scheduled', 'processing', 'publishing')
EDITABLE = ('draft', 'scheduled', 'failed')
CAPTION_MAX = 2200
HASHTAGS_MAX = 30
MENTIONS_MAX = 20
CAROUSEL_MAX = 10
PROCESSING_TIMEOUT = timedelta(minutes=30)
SCHEDULE_MAX = timedelta(days=75)
UPLOADS = {
    'jpg': ('image', 'image/jpeg', (b'\xff\xd8\xff',)),
    'jpeg': ('image', 'image/jpeg', (b'\xff\xd8\xff',)),
    'mp4': ('video', 'video/mp4', None),
    'mov': ('video', 'video/quicktime', None),
}


# ---------- uploaded media ----------
def save_media(workspace_id, user_id, upload):
    """Stores an upload for publication. Instagram accepts JPEG images and MP4/MOV videos."""
    name = (upload.filename or '').strip()
    extension = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if extension not in UPLOADS:
        raise APIError('Use imagens JPEG ou vídeos MP4/MOV. Outras imagens são convertidas no navegador.', 422)
    kind, content_type, magic = UPLOADS[extension]
    limit = current_app.config['PROJECT_FILE_MAX_BYTES']
    content = upload.read(limit + 1)
    if not content:
        raise APIError('O arquivo está vazio.', 422)
    if len(content) > limit:
        raise APIError('O arquivo deve ter até 14 MB. Para vídeos maiores, informe um link público.', 413)
    if magic and not any(content.startswith(sig) for sig in magic):
        raise APIError('O conteúdo do arquivo não corresponde à extensão.', 422)
    if kind == 'video' and content[4:8] not in (b'ftyp', b'moov', b'wide', b'mdat'):
        raise APIError('O conteúdo do arquivo não corresponde à extensão.', 422)
    key = f'instagram/{workspace_id}/{uuid.uuid4().hex}.{extension}'
    path = storage_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    row = InstagramMedia(
        workspace_id=workspace_id,
        filename=name[:255],
        kind=kind,
        content_type=content_type,
        size=len(content),
        storage_key=key,
        public_token=secrets.token_urlsafe(32),
        created_by_id=user_id,
    )
    db.session.add(row)
    db.session.flush()
    return row


def media_in_use(row):
    return any(
        any(item.get('media_id') == row.id for item in (post.items or []))
        for post in InstagramPost.query.filter(
            InstagramPost.workspace_id == row.workspace_id, InstagramPost.status.in_(PENDING + ('draft', 'failed'))
        )
    )


def delete_media(row):
    if media_in_use(row):
        raise APIError('Este arquivo está em uma publicação pendente.', 409)
    delete_bytes(row.storage_key)
    db.session.delete(row)


def public_media(token):
    """The file Instagram downloads. Served only while a post that uses it is waiting to be published."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{30,100}', token or ''):
        return None
    row = InstagramMedia.query.filter_by(public_token=token).first()
    if not row:
        return None
    pending = InstagramPost.query.filter(
        InstagramPost.workspace_id == row.workspace_id, InstagramPost.status.in_(PENDING)
    ).all()
    if not any(any(item.get('media_id') == row.id for item in (post.items or [])) for post in pending):
        return None
    return row


def public_url(row):
    return current_app.config['APP_URL'] + '/api/public/media/' + row.public_token


# ---------- posts ----------
def validate_caption(caption):
    if not isinstance(caption, str):
        raise APIError('Legenda inválida.', 422)
    caption = caption.strip()
    if len(caption) > CAPTION_MAX:
        raise APIError(f'A legenda aceita até {CAPTION_MAX} caracteres.', 422)
    if len(re.findall(r'(?:^|\s)#\w', caption)) > HASHTAGS_MAX:
        raise APIError(f'O Instagram aceita até {HASHTAGS_MAX} hashtags por publicação.', 422)
    if len(re.findall(r'(?:^|\s)@[\w.]', caption)) > MENTIONS_MAX:
        raise APIError(f'O Instagram aceita até {MENTIONS_MAX} menções por publicação.', 422)
    return caption


def validate_items(workspace_id, media_type, items):
    if not isinstance(items, list) or not items:
        raise APIError('Adicione a mídia da publicação.', 422)
    clean = []
    for item in items:
        if not isinstance(item, dict):
            raise APIError('Mídia inválida.', 422)
        if item.get('media_id'):
            row = InstagramMedia.query.filter_by(workspace_id=workspace_id, id=str(item['media_id'])).first()
            if not row:
                raise APIError('Arquivo não encontrado.', 404)
            clean.append({'media_id': row.id, 'kind': row.kind})
            continue
        url, kind = item.get('url'), item.get('kind')
        parsed = urlparse(url) if isinstance(url, str) else None
        if not parsed or parsed.scheme != 'https' or not parsed.hostname or len(url) > 2000:
            raise APIError('Informe um link público HTTPS para a mídia.', 422)
        if kind not in ('image', 'video'):
            raise APIError('Informe se o link é de imagem ou vídeo.', 422)
        clean.append({'url': url, 'kind': kind})
    kinds = [item['kind'] for item in clean]
    if media_type == 'IMAGE' and kinds != ['image']:
        raise APIError('Uma publicação de imagem usa exatamente uma imagem.', 422)
    if media_type == 'REELS' and kinds != ['video']:
        raise APIError('Um Reel usa exatamente um vídeo.', 422)
    if media_type == 'CAROUSEL' and not 2 <= len(clean) <= CAROUSEL_MAX:
        raise APIError(f'Um carrossel usa de 2 a {CAROUSEL_MAX} imagens ou vídeos.', 422)
    return clean


def publishing_connection(workspace_id, connection_id):
    row = connections.active_connection(workspace_id, connection_id)
    if not row.to_dict()['can_publish']:
        raise APIError('Reconecte este Instagram para autorizar publicações.', 409)
    return row


def apply(post, data, workspace_id):
    """Validates and copies editable fields. Raises before changing anything."""
    connection_id = data.get('connection_id', post.connection_id)
    media_type = data.get('media_type', post.media_type)
    if media_type not in MEDIA_TYPES:
        raise APIError('Tipo de publicação inválido.', 422)
    connection = publishing_connection(workspace_id, connection_id)
    caption = validate_caption(data.get('caption', post.caption or ''))
    items = validate_items(workspace_id, media_type, data.get('items', post.items))
    scheduled_at = data.get('scheduled_at', post.scheduled_at)
    post.connection_id, post.media_type, post.caption, post.items = connection.id, media_type, caption, items
    post.scheduled_at = scheduled_at
    return post


def schedule(post, when=None):
    """Queues a post for the worker: now, or at a future moment (Instagram has no native scheduling)."""
    when = when or now()
    if when > now() + SCHEDULE_MAX:
        raise APIError('Agende com até 75 dias de antecedência.', 422)
    if when < now() - timedelta(minutes=5):
        raise APIError('Escolha um horário futuro.', 422)
    publishing_connection(post.workspace_id, post.connection_id)
    post.status, post.scheduled_at, post.error = 'scheduled', when, None
    post.containers, post.processing_since = {}, None


def public_post(post):
    result = post.to_dict()
    media = {
        row.id: row
        for row in InstagramMedia.query.filter(
            InstagramMedia.workspace_id == post.workspace_id,
            InstagramMedia.id.in_([i['media_id'] for i in post.items or [] if i.get('media_id')] or ['']),
        )
    }
    result['items'] = [
        {**item, **({'filename': media[item['media_id']].filename} if item.get('media_id') in media else {})}
        for item in post.items or []
    ]
    return result


# ---------- worker ----------
def item_url(post, item):
    if item.get('url'):
        return item['url']
    row = InstagramMedia.query.filter_by(workspace_id=post.workspace_id, id=item.get('media_id')).first()
    if not row:
        raise APIError('Um arquivo da publicação foi removido.', 422)
    return public_url(row)


def create_container(connection, token, post, item, carousel=False):
    params = {}
    if item['kind'] == 'image':
        params['image_url'] = item_url(post, item)
    else:
        params['video_url'] = item_url(post, item)
        params['media_type'] = 'VIDEO' if carousel else 'REELS'
        if not carousel:
            params['share_to_feed'] = 'true'
    if carousel:
        params['is_carousel_item'] = 'true'
    elif post.caption:
        params['caption'] = post.caption
    data = client.graph(connection.instagram_id + '/media', token, method='POST', detail=True, params=params)
    if not str(data.get('id') or '').isdigit():
        raise APIError('O Instagram não criou o contêiner da mídia.', 502)
    return str(data['id'])


def container_state(token, container_id):
    data = client.graph(container_id, token, params={'fields': 'status_code,status'})
    return str(data.get('status_code') or ''), str(data.get('status') or '')[:300]


def fail(post, message):
    post.status, post.error = 'failed', str(message)[:500]


def advance(post):
    """One step for one post. Commits checkpoints itself."""
    connection = db.session.get(InstagramConnection, post.connection_id)
    if not connections.usable(connection) or connection.workspace_id != post.workspace_id:
        fail(post, 'O Instagram desta publicação foi desconectado. Reconecte e agende novamente.')
        return
    token = connections.token(connection)
    state = dict(post.containers or {})
    if post.status == 'scheduled':
        post.status, post.processing_since = 'processing', now()
        if post.media_type == 'CAROUSEL':
            state['children'] = [create_container(connection, token, post, item, True) for item in post.items]
        else:
            state['parent'] = create_container(connection, token, post, post.items[0])
        post.containers = state
        db.session.commit()
    if post.processing_since and post.processing_since < now() - PROCESSING_TIMEOUT:
        fail(post, 'O Instagram não terminou de processar a mídia em 30 minutos.')
        return
    pending = [state['parent']] if state.get('parent') else list(state.get('children') or [])
    for container in pending:
        code, detail = container_state(token, container)
        if code in ('ERROR', 'EXPIRED'):
            fail(post, 'O Instagram recusou a mídia' + (': ' + detail if detail else '.'))
            return
        if code != 'FINISHED':
            return  # Still processing (videos take a while); the next pass checks again.
    if not state.get('parent'):
        params = {'media_type': 'CAROUSEL', 'children': ','.join(state['children'])}
        if post.caption:
            params['caption'] = post.caption
        data = client.graph(connection.instagram_id + '/media', token, method='POST', detail=True, params=params)
        if not str(data.get('id') or '').isdigit():
            raise APIError('O Instagram não criou o carrossel.', 502)
        state['parent'] = str(data['id'])
        post.containers = state
        db.session.commit()
        return  # Check the carousel container's own status on the next pass.
    post.status = 'publishing'
    db.session.commit()  # Persist the claim before the irreversible call; never publish twice.
    try:
        data = client.graph(
            connection.instagram_id + '/media_publish',
            token,
            method='POST',
            detail=True,
            params={'creation_id': state['parent']},
        )
    except client.GraphError as error:
        fail(post, error.message)  # Instagram answered with a refusal: nothing was published.
        return
    except Exception as error:  # delivery boundary: no answer means we cannot know
        current_app.logger.warning('instagram publish without confirmation: %s', type(error).__name__)
        post.status = 'unknown'
        post.error = 'Publicação sem confirmação. Confira no Instagram antes de tentar de novo.'
        return
    if not data.get('id'):
        post.status = 'unknown'
        post.error = 'Publicação sem confirmação. Confira no Instagram antes de tentar de novo.'
        return
    post.status, post.ig_media_id, post.published_at, post.error = 'published', str(data['id'])[:80], now(), None
    try:
        details = client.graph(post.ig_media_id, token, params={'fields': 'permalink'})
        post.permalink = details.get('permalink')
    except APIError:
        pass  # The post is live; the link is only a convenience.


def process(limit=5):
    """Advances due posts. Publishing is always an explicit user action, so it runs independently of the
    worker's message dispatch switch."""
    # A worker that died between the claim and the publish call leaves `publishing`: never guess, report it.
    stale = InstagramPost.query.filter(
        InstagramPost.status == 'publishing', InstagramPost.updated_at < now() - timedelta(minutes=10)
    ).all()
    for post in stale:
        post.status = 'unknown'
        post.error = 'Publicação sem confirmação. Confira no Instagram antes de tentar de novo.'
    if stale:
        db.session.commit()
    ids = [
        row.id
        for row in InstagramPost.query.filter(
            db.or_(
                db.and_(InstagramPost.status == 'scheduled', InstagramPost.scheduled_at <= now()),
                InstagramPost.status == 'processing',
            )
        )
        .order_by(InstagramPost.scheduled_at)
        .limit(limit)
        .all()
    ]
    db.session.rollback()
    done = 0
    for identifier in ids:
        post = InstagramPost.query.filter_by(id=identifier).with_for_update(skip_locked=True).first()
        if not post or post.status not in ('scheduled', 'processing'):
            db.session.rollback()
            continue
        try:
            advance(post)
            db.session.commit()
        except Exception as error:
            db.session.rollback()
            post = InstagramPost.query.filter_by(id=identifier).with_for_update().first()
            if post and post.status in ('scheduled', 'processing'):
                fail(post, error.message if isinstance(error, APIError) else 'Falha ao preparar a publicação.')
                db.session.commit()
            current_app.logger.warning('instagram_post_failed post=%s type=%s', identifier, type(error).__name__)
        done += 1
    return done


def publishing_limit(connection):
    data = client.graph(
        connection.instagram_id + '/content_publishing_limit',
        connections.token(connection),
        params={'fields': 'quota_usage,config'},
    )
    row = (data.get('data') or [{}])[0]
    config = row.get('config') or {}
    return {'used': int(row.get('quota_usage') or 0), 'total': int(config.get('quota_total') or 100)}
