"""Instagram content: uploaded media, posts (now or scheduled) and metrics, per connected account.

The whole team prepares drafts and reads metrics; scheduling and publishing on a client's profile is reserved
to owners and admins.
"""

from datetime import datetime, timezone

from flask import Blueprint, g, request, send_file

from ..common import APIError, audit, get, query, require
from ..extensions import db, limiter
from ..models import InstagramConnection, InstagramMedia, InstagramPost
from ..services import instagram as service
from ..services.instagram import insights, publishing
from ..services.projects import storage_path

bp = Blueprint('instagram_content', __name__)

POST_STATUSES = ('draft', 'scheduled', 'processing', 'publishing', 'published', 'failed', 'unknown')


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError('Envie um objeto JSON válido.')
    return data


def moment(value):
    if value in (None, ''):
        return None
    if not isinstance(value, str):
        raise APIError('Data inválida.', 422)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise APIError('Data inválida.', 422) from None
    if parsed.tzinfo is None:
        raise APIError('Informe a data com fuso horário.', 422)
    return parsed.astimezone(timezone.utc)


def file_response(row, cache='private, no-store'):
    path = storage_path(row.storage_key)
    if not path.is_file():
        raise APIError('Arquivo indisponível.', 404)
    response = send_file(path, mimetype=row.content_type, download_name=row.filename, max_age=0, conditional=True)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'none'; sandbox"
    response.headers['Cache-Control'] = cache
    return response


# ---------- media ----------
@bp.post('/instagram/media')
@require()
@limiter.limit('120 per hour')
def media_upload():
    upload = request.files.get('file')
    if not upload:
        raise APIError('Envie um arquivo.')
    row = publishing.save_media(g.workspace_id, g.user.id, upload)
    db.session.commit()
    return row.to_dict(), 201


@bp.get('/instagram/media/<uuid:media_id>/file')
@require()
def media_file(media_id):
    return file_response(get(InstagramMedia, media_id))


@bp.delete('/instagram/media/<uuid:media_id>')
@require()
def media_delete(media_id):
    publishing.delete_media(get(InstagramMedia, media_id))
    db.session.commit()
    return {'deleted': True}


@bp.get('/public/instagram-media/<token>')
@limiter.limit('120 per minute')
def media_public(token):
    """Instagram's servers download the post media here. No session; the link works only while the post
    that uses the file is waiting to be published."""
    row = publishing.public_media(token)
    if not row:
        raise APIError('Arquivo indisponível.', 404)
    return file_response(row, cache='public, max-age=600')


# ---------- posts ----------
@bp.get('/instagram/posts')
@require()
def posts():
    q = query(InstagramPost)
    if request.args.get('connection_id'):
        q = q.filter_by(connection_id=request.args['connection_id'])
    status = request.args.get('status')
    if status:
        if status not in POST_STATUSES:
            raise APIError('Situação inválida.', 422)
        q = q.filter_by(status=status)
    rows = q.order_by(db.func.coalesce(InstagramPost.scheduled_at, InstagramPost.created_at).desc()).limit(200).all()
    return {'items': [publishing.public_post(row) for row in rows]}


def can_schedule():
    if g.role not in ('owner', 'admin'):
        raise APIError('Somente proprietários e administradores publicam no Instagram.', 403)


@bp.post('/instagram/posts')
@require()
@limiter.limit('60 per hour')
def post_create():
    data = body()
    action = data.get('action', 'draft')
    if action not in ('draft', 'schedule', 'publish'):
        raise APIError('Ação inválida.', 422)
    if action != 'draft':
        can_schedule()
    post = InstagramPost(workspace_id=g.workspace_id, created_by_id=g.user.id, status='draft', items=[], containers={})
    publishing.apply(
        post,
        {
            'connection_id': data.get('connection_id'),
            'media_type': data.get('media_type'),
            'caption': data.get('caption', ''),
            'items': data.get('items'),
            'scheduled_at': moment(data.get('scheduled_at')),
        },
        g.workspace_id,
    )
    if action == 'schedule' and not post.scheduled_at:
        raise APIError('Escolha a data e o horário da publicação.', 422)
    if action != 'draft':
        publishing.schedule(post, None if action == 'publish' else post.scheduled_at)
    db.session.add(post)
    db.session.flush()
    audit('instagram.post.' + action, post, {'connection_id': post.connection_id})
    db.session.commit()
    return publishing.public_post(post), 201


@bp.patch('/instagram/posts/<uuid:post_id>')
@require()
def post_update(post_id):
    post = get(InstagramPost, post_id, lock=True)
    if post.status not in publishing.EDITABLE:
        raise APIError('Esta publicação não pode mais ser editada.', 409)
    if post.status == 'scheduled':
        can_schedule()
    data = body()
    fields = {key: data[key] for key in ('connection_id', 'media_type', 'caption', 'items') if key in data}
    if 'scheduled_at' in data:
        fields['scheduled_at'] = moment(data['scheduled_at'])
    publishing.apply(post, fields, g.workspace_id)
    if post.status == 'scheduled':
        publishing.schedule(post, post.scheduled_at)
    elif post.status == 'failed':
        post.status, post.error = 'draft', None
    db.session.commit()
    return publishing.public_post(post)


@bp.post('/instagram/posts/<uuid:post_id>/schedule')
@require()
@limiter.limit('60 per hour')
def post_schedule(post_id):
    can_schedule()
    post = get(InstagramPost, post_id, lock=True)
    if post.status not in ('draft', 'scheduled', 'failed'):
        raise APIError('Esta publicação já foi enviada ao Instagram.', 409)
    data = request.get_json(silent=True) or {}
    when = moment(data.get('scheduled_at'))
    publishing.schedule(post, when)
    audit('instagram.post.' + ('schedule' if when else 'publish'), post, {'connection_id': post.connection_id})
    db.session.commit()
    return publishing.public_post(post)


@bp.post('/instagram/posts/<uuid:post_id>/cancel')
@require()
def post_cancel(post_id):
    can_schedule()
    post = get(InstagramPost, post_id, lock=True)
    if post.status != 'scheduled':
        raise APIError('Somente publicações agendadas podem voltar para rascunho.', 409)
    post.status = 'draft'
    audit('instagram.post.cancel', post)
    db.session.commit()
    return publishing.public_post(post)


@bp.delete('/instagram/posts/<uuid:post_id>')
@require()
def post_delete(post_id):
    post = get(InstagramPost, post_id, lock=True)
    if post.status in ('processing', 'publishing'):
        raise APIError('Aguarde o Instagram concluir esta publicação.', 409)
    if post.status == 'scheduled':
        can_schedule()
    # Removes the record from the Antares only; a published post stays on Instagram.
    audit('instagram.post.delete', post, {'status': post.status})
    db.session.delete(post)
    db.session.commit()
    return {'deleted': True}


@bp.get('/instagram/accounts/<uuid:connection_id>/publishing-limit')
@require()
@limiter.limit('30 per minute')
def publishing_limit(connection_id):
    row = get(InstagramConnection, connection_id)
    if not service.usable(row):
        raise APIError('Reconecte este Instagram.', 409)
    return publishing.publishing_limit(row)


# ---------- metrics ----------
@bp.get('/instagram/accounts/<uuid:connection_id>/insights')
@require()
@limiter.limit('30 per minute')
def account_insights(connection_id):
    row = get(InstagramConnection, connection_id)
    if not service.usable(row):
        raise APIError('Reconecte este Instagram.', 409)
    try:
        days = int(request.args.get('days', 30))
    except ValueError:
        raise APIError('Período inválido.', 422) from None
    force = request.args.get('refresh') == '1'
    snapshot = insights.snapshot(row, days, force=force)
    db.session.commit()
    return insights.public(snapshot, row)
