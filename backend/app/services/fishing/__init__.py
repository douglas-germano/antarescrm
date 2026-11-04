"""Manual-link MVP. Account-scoped actions and durable worker processing."""

import base64
import binascii
import re
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from flask import current_app
from marshmallow import ValidationError
from sqlalchemy import func

from ...common import APIError
from ...extensions import db
from ...models import FishingDraft, FishingPost, FishingSettings, FishingUsage, Workspace, now
from ..booking import lock
from . import ai

ACTIVE = ('novo', 'processando', 'na_fila')


def settings(account):
    return account.query(FishingSettings).first()


def save_settings(account, data):
    data = dict(data)
    data['blocked_authors'] = list(dict.fromkeys(name.lstrip('@').lower() for name in data['blocked_authors']))
    if any(not re.fullmatch(r'[a-z0-9_.]{1,30}', name) for name in data['blocked_authors']):
        raise APIError('Use nomes de perfil válidos na lista de bloqueados.', 422)
    lock('fishing:' + account.workspace_id)
    row = settings(account)
    if not row:
        row = FishingSettings(workspace_id=account.workspace_id)
        db.session.add(row)
    for key, value in data.items():
        setattr(row, key, value)
    db.session.flush()
    return row


def settings_copy(account):
    row = settings(account)
    if row:
        result = row.to_dict()
    else:
        result = {
            column.name: column.default.arg(None) if callable(column.default.arg) else column.default.arg
            for column in FishingSettings.__table__.columns
            if column.default is not None and column.name not in ('id', 'created_at', 'updated_at')
        }
    result['provider_ready'] = ai.configured()
    return result


def day_start(workspace_id):
    zone = ZoneInfo(db.session.get(Workspace, workspace_id).timezone)
    return datetime.combine(now().astimezone(zone).date(), time.min, zone).astimezone(timezone.utc)


def validate_image(value):
    if not value:
        return None
    match = re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)', value)
    if not match:
        raise APIError('Anexe uma imagem PNG, JPEG ou WebP de até 4 MB.', 422)
    try:
        data = base64.b64decode(match[2], validate=True)
    except (ValueError, binascii.Error):
        raise APIError('Imagem inválida.', 422) from None
    signatures = {
        'png': data.startswith(b'\x89PNG\r\n\x1a\n'),
        'jpeg': data.startswith(b'\xff\xd8\xff'),
        'webp': data.startswith(b'RIFF') and data[8:12] == b'WEBP',
    }
    if len(data) > 4 * 1024 * 1024 or not signatures[match[1]]:
        raise APIError('Imagem inválida ou maior que 4 MB.', 422)
    return value


def create_post(account, data):
    lock('fishing:' + account.workspace_id)
    config = settings(account)
    if not config or not config.enabled or not ai.configured():
        raise APIError('Configure e habilite a Pesca antes de adicionar posts.', 422)
    parsed = urlsplit(data['url'].strip())
    match = re.fullmatch(r'/(p|reel|tv)/([A-Za-z0-9_-]{1,90})/?', parsed.path)
    if parsed.scheme != 'https' or parsed.netloc not in ('instagram.com', 'www.instagram.com') or not match:
        raise APIError('Use o link HTTPS de um post ou reel do Instagram.', 422)
    author = data['author'].lstrip('@').lower()
    if author and (author == config.own_username.lower() or author in config.blocked_authors):
        raise APIError('Este perfil está bloqueado ou pertence à própria marca.', 422)
    if account.query(FishingPost).filter_by(media_id=match[2]).first():
        raise APIError('Este post já foi adicionado.', 409)
    if account.query(FishingPost).filter(FishingPost.status.in_(ACTIVE)).count() >= 200:
        raise APIError('Revise a fila antes de adicionar mais posts (limite de 200).', 422)
    row = FishingPost(
        workspace_id=account.workspace_id,
        url=f'https://www.instagram.com/{match[1]}/{match[2]}/',
        media_id=match[2],
        author=author,
        caption=data['caption'],
        image_data=validate_image(data['image_data']),
        user_id=account.user_id,
    )
    db.session.add(row)
    db.session.flush()
    return row


def serialize(account, row):
    result = row.to_dict()
    drafts = account.query(FishingDraft).filter_by(post_id=row.id)
    generation = drafts.with_entities(func.max(FishingDraft.generation)).scalar()
    result['drafts'] = [
        draft.to_dict() for draft in drafts.filter_by(generation=generation).order_by(FishingDraft.created_at)
    ]
    return result


def add_latest_drafts(account, items):
    if not items:
        return
    ids = [item['id'] for item in items]
    latest = (
        account.query(FishingDraft)
        .filter(FishingDraft.post_id.in_(ids))
        .with_entities(FishingDraft.post_id, func.max(FishingDraft.generation).label('generation'))
        .group_by(FishingDraft.post_id)
        .subquery()
    )
    drafts = (
        account.query(FishingDraft)
        .join(latest, (FishingDraft.post_id == latest.c.post_id) & (FishingDraft.generation == latest.c.generation))
        .order_by(FishingDraft.created_at)
        .all()
    )
    grouped = {identifier: [] for identifier in ids}
    for draft in drafts:
        grouped[draft.post_id].append(draft.to_dict())
    for item in items:
        item['drafts'] = grouped[item['id']]


def expire(workspace_id=None):
    old = FishingPost.query.filter(FishingPost.created_at < now() - timedelta(hours=48))
    if workspace_id:
        old = old.filter_by(workspace_id=workspace_id)
    old.filter(FishingPost.image_data.is_not(None)).update({'image_data': None}, synchronize_session=False)
    return old.filter(FishingPost.status.in_(ACTIVE)).update({'status': 'expirado'}, synchronize_session=False)


def recent_texts(workspace_id):
    return [
        r.published_text
        for r in FishingPost.query.filter_by(workspace_id=workspace_id, status='publicado')
        .order_by(FishingPost.published_at.desc())
        .limit(50)
        if r.published_text
    ]


def valid_text(value, config, history):
    normalized = ' '.join(value.casefold().split())
    if (
        not value.strip()
        or len(value) > 220
        or re.search(r'https?://|www\.|[@#]|\b\w+\.(com|br|net|org)\b|R\$|\b\d+[,.]\d{2}\b', value, re.I)
    ):
        return False
    banned = [*config.forbidden_words, 'chama no direct', 'que post incrível', 'amei', 'conteúdo top']
    if any(word.casefold() in normalized for word in banned):
        return False
    return all(SequenceMatcher(None, normalized, ' '.join(text.casefold().split())).ratio() < 0.82 for text in history)


def open_post(account, row, data):
    lock('fishing:' + account.workspace_id)
    db.session.refresh(row)
    config = settings(account)
    if not config or not config.enabled or row.status != 'na_fila':
        raise APIError('Este card não está disponível para comentar.', 409)
    if row.created_at < now() - timedelta(hours=48):
        raise APIError('Este card expirou.', 409)
    if row.opened_at:
        if row.user_id != account.user_id:
            raise APIError('Outra pessoa está revisando este card.', 409)
        raise APIError('Confirme se publicou ou pule este card antes de abrir novamente.', 409)
    published = account.query(FishingPost).filter_by(status='publicado')
    reserved = account.query(FishingPost).filter(FishingPost.opened_at.is_not(None), FishingPost.status == 'na_fila')
    start = day_start(account.workspace_id)
    count = published.filter(FishingPost.published_at >= start).count() + reserved.count()
    if count >= config.daily_limit:
        raise APIError('O limite diário de comentários foi atingido.', 409)
    if row.author and (row.author in config.blocked_authors or row.author == config.own_username.lower()):
        raise APIError('Este perfil foi bloqueado ou pertence à própria marca.', 409)
    if row.author and (
        published.filter(
            FishingPost.author == row.author, FishingPost.published_at >= now() - timedelta(days=7)
        ).first()
        or reserved.filter_by(author=row.author).first()
    ):
        raise APIError('Este autor já recebeu um comentário nos últimos 7 dias ou está em revisão.', 409)
    draft = account.get(FishingDraft, data['draft_id'])
    generation = (
        account.query(FishingDraft).filter_by(post_id=row.id).with_entities(func.max(FishingDraft.generation)).scalar()
    )
    if draft.post_id != row.id or draft.generation != generation:
        raise APIError('Escolha uma opção atual deste card.', 422)
    if not valid_text(data['text'], config, recent_texts(account.workspace_id)):
        raise APIError('Revise o texto: há termos proibidos, propaganda ou semelhança com comentários recentes.', 422)
    row.opened_at, row.user_id = now(), account.user_id
    row.selected_draft_id, row.published_text = draft.id, data['text'].strip()
    row.edited = row.published_text != draft.text
    warning = published.filter(FishingPost.published_at >= now() - timedelta(minutes=10)).count() >= 5
    return {
        'post': serialize(account, row),
        'warning': 'Mais de 5 comentários em 10 minutos. Considere uma pausa.' if warning else None,
    }


def decide(account, row, action):
    lock('fishing:' + account.workspace_id)
    db.session.refresh(row)
    if action == 'desfazer':
        if row.status != 'publicado' or row.user_id != account.user_id:
            raise APIError('Somente quem confirmou pode desfazer o registro.', 409)
        row.status, row.published_at = 'pulado', None
        return
    if row.status not in ('novo', 'na_fila', 'descartado', 'erro'):
        raise APIError('Este card já foi decidido ou está sendo processado.', 409)
    if row.opened_at and row.user_id != account.user_id:
        raise APIError('Somente quem abriu o post pode confirmar a publicação.', 409)
    if action == 'publicado':
        if not row.opened_at or row.status != 'na_fila':
            raise APIError('Abra o post com uma opção revisada antes de confirmar.', 409)
        row.published_at = now()
    row.status, row.decided_at, row.user_id, row.image_data = action, now(), account.user_id, None


def regenerate(account, row):
    lock('fishing:' + account.workspace_id)
    db.session.refresh(row)
    config = settings(account)
    if not config or not config.enabled or not ai.configured():
        raise APIError('Habilite e configure a IA antes de gerar.', 422)
    if row.status not in ('na_fila', 'descartado', 'erro') or row.opened_at:
        raise APIError('Este card não pode ser gerado novamente.', 409)
    if row.created_at < now() - timedelta(hours=48):
        raise APIError('Este card expirou. Adicione um post recente.', 409)
    row.status, row.error = 'novo', None


def metrics(account):
    posts = account.query(FishingPost)
    counts = dict(posts.with_entities(FishingPost.status, func.count()).group_by(FishingPost.status).all())
    total = sum(counts.values())
    published = counts.get('publicado', 0)
    usage = account.query(FishingUsage)
    tokens, cost, unknown = usage.with_entities(
        func.coalesce(func.sum(FishingUsage.tokens), 0),
        func.sum(FishingUsage.cost_usd),
        func.count().filter(FishingUsage.cost_usd.is_(None)),
    ).one()
    return {
        'counts': counts,
        'total': total,
        'published_today': posts.filter(
            FishingPost.status == 'publicado', FishingPost.published_at >= day_start(account.workspace_id)
        ).count(),
        'edit_rate': round(posts.filter_by(status='publicado', edited=True).count() / published * 100, 1)
        if published
        else 0,
        'approval_rate': round(published / max(1, posts.filter(FishingPost.queued_at.is_not(None)).count()) * 100, 1),
        'tokens': tokens,
        'cost_usd': str(cost) if cost is not None else None,
        'unknown_cost_calls': unknown,
        'ai_calls_today': usage.filter(FishingUsage.created_at >= day_start(account.workspace_id)).count(),
    }


def invoke(row, config, phase, context):
    lock('fishing:' + row.workspace_id)
    db.session.refresh(config)
    if not config.enabled:
        raise APIError('Pesca desabilitada durante o processamento.', 409)
    used = (
        FishingUsage.query.filter_by(workspace_id=row.workspace_id)
        .filter(FishingUsage.created_at >= day_start(row.workspace_id))
        .count()
    )
    if used >= config.daily_ai_limit:
        raise APIError('Limite diário de chamadas de IA atingido. Gere novamente amanhã.', 409)
    model = current_app.config['FISHING_TRIAGE_MODEL' if phase == 'triage' else 'FISHING_DRAFT_MODEL']
    usage = FishingUsage(workspace_id=row.workspace_id, post_id=row.id, model=model, phase=phase)
    db.session.add(usage)
    db.session.commit()  # Reserve a call before network I/O; never hold a lock across provider latency.
    body = ai.complete(phase, model, context, row.image_data)
    metadata = body.get('usage') or {}
    if not isinstance(metadata, dict):
        metadata = {}
    try:
        usage.tokens = min(100_000_000, max(0, int(metadata.get('total_tokens', 0))))
        cost = Decimal(str(metadata['cost'])) if metadata.get('cost') is not None else None
        usage.cost_usd = cost if cost is not None and cost.is_finite() and 0 <= cost < Decimal('10000000') else None
    except (TypeError, ValueError, InvalidOperation):
        usage.cost_usd = None
    db.session.commit()  # Account for malformed/rejected model output as well.
    lock('fishing:' + row.workspace_id)
    db.session.refresh(row)
    db.session.refresh(config)
    if not config.enabled:
        raise APIError('Pesca desabilitada durante o processamento.', 409)
    if row.status != 'processando' or row.created_at < now() - timedelta(hours=48):
        raise APIError('O card expirou ou deixou de estar em processamento.', 409)
    return ai.parse(body, phase)


def process(limit=1):
    expire()
    # An interrupted request has unknown billing; make it reviewable instead of retrying automatically.
    FishingPost.query.filter_by(status='processando').filter(
        FishingPost.processing_at < now() - timedelta(minutes=5)
    ).update(
        {'status': 'erro', 'error': 'Processamento interrompido. Revise antes de gerar novamente.'},
        synchronize_session=False,
    )
    db.session.commit()
    if not ai.configured():
        return 0
    processed = 0
    for _ in range(limit):
        row = (
            FishingPost.query.join(FishingSettings, FishingSettings.workspace_id == FishingPost.workspace_id)
            .join(Workspace, Workspace.id == FishingPost.workspace_id)
            .filter(FishingPost.status == 'novo', FishingSettings.enabled.is_(True), Workspace.active.is_(True))
            .order_by(FishingPost.created_at)
            .with_for_update(skip_locked=True, of=FishingPost)
            .first()
        )
        if not row:
            db.session.commit()
            break
        row.status, row.processing_at = 'processando', now()
        db.session.commit()
        config = FishingSettings.query.filter_by(workspace_id=row.workspace_id).one()
        context = {
            'marca': {
                key: getattr(config, key)
                for key in (
                    'brand_name',
                    'brand_profile',
                    'tone',
                    'examples',
                    'allowed_topics',
                    'forbidden_words',
                    'objective',
                )
            },
            'post': {'legenda': row.caption, 'autor': row.author, 'fonte': 'link'},
            'ultimos_comentarios': recent_texts(row.workspace_id)[:10],
        }
        try:
            triage = invoke(row, config, 'triage', context)
            row.score, row.reason = triage['nota'], triage['motivo']
            if row.score < config.score_threshold:
                row.status = 'descartado'
            else:
                result = invoke(row, config, 'draft', context)
                row.summary = result['resumo_do_post']
                options, history = [], recent_texts(row.workspace_id)
                if not result['pular']:
                    if len(result['opcoes']) != 3 or {o['tipo'] for o in result['opcoes']} != {
                        'acrescenta',
                        'pergunta',
                        'reacao',
                    }:
                        raise APIError('A IA não retornou as três opções esperadas.', 502)
                    for option in result['opcoes']:
                        if valid_text(option['texto'], config, history + [o['texto'] for o in options]):
                            options.append(option)
                if not options:
                    row.status, row.reason = 'descartado', 'Nenhum comentário adequado passou nas verificações.'
                else:
                    generation = (
                        db.session.query(func.max(FishingDraft.generation))
                        .filter_by(post_id=row.id, workspace_id=row.workspace_id)
                        .scalar()
                        or 0
                    ) + 1
                    for option in options:
                        db.session.add(
                            FishingDraft(
                                workspace_id=row.workspace_id,
                                post_id=row.id,
                                generation=generation,
                                kind=option['tipo'],
                                text=option['texto'],
                            )
                        )
                    row.status, row.queued_at, row.error = 'na_fila', row.queued_at or now(), None
        except (APIError, ValidationError) as error:
            if row.status == 'processando':
                row.status = 'erro'
            row.error = (
                error.message if isinstance(error, APIError) else 'A IA retornou dados fora do formato esperado.'
            )
        db.session.commit()
        processed += 1
    return processed
