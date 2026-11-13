"""MCP tools for AI clients: conversations, sending, Instagram posts, comments and metrics.

Every tool runs inside the token's account, as the user who created the token, through the same services the
screens use: the 24-hour Instagram window, idempotent sends, publishing claims and account isolation all apply.
Irreversible tools (send, publish, reply) require `confirm: true`, carry destructive hints so clients ask the
person first, are audited per token and share an hourly budget.
"""

import uuid
from datetime import datetime, timedelta, timezone

from flask import g

from ..common import APIError, audit
from ..extensions import db
from ..models import (
    InboxMessage,
    InboxThread,
    InstagramComment,
    InstagramConnection,
    InstagramPost,
    WhatsAppConnection,
    WhatsAppConversation,
    WhatsAppMessage,
    Workspace,
    now,
)
from ..tenancy import AccountContext
from . import api_tokens, inbox, instagram, messaging
from .instagram import client as instagram_client
from .instagram import comments as instagram_comments
from .instagram import insights, publishing

PROTOCOL_VERSIONS = ('2025-06-18', '2025-03-26', '2024-11-05')
INSTRUCTIONS = (
    'Ferramentas do Antares CRM para a conta vinculada a este token. Antes de enviar mensagens, publicar ou '
    'responder comentários, mostre o texto à pessoa e só chame a ferramenta com confirm=true depois que ela '
    'aprovar. No Instagram, respostas a mensagens só são aceitas até 24 horas após a última mensagem do cliente.'
)

READ = {'readOnlyHint': True, 'destructiveHint': False, 'openWorldHint': False}
ACT = {'readOnlyHint': False, 'destructiveHint': True, 'idempotentHint': False, 'openWorldHint': True}
CONFIRM = {'type': 'boolean', 'const': True, 'description': 'true somente depois que a pessoa aprovar a ação.'}
ACCOUNT = {'type': 'string', 'description': 'ID do perfil do Instagram (list_instagram_accounts).'}


def account():
    return AccountContext(workspace_id=g.workspace_id, user_id=g.user.id)


def need(scope):
    if scope not in (g.api_token.scopes or []):
        raise APIError(f'Este token não tem a permissão {scope}.', 403)


def act(action, details):
    """Budget and audit trail for an irreversible action, written before it runs."""
    api_tokens.check_budget(g.api_token)
    audit('mcp.action.' + action, g.api_token, details)
    db.session.commit()


def iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def clamp(value, low, high, default):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def instagram_account(identifier):
    row = InstagramConnection.query.filter_by(workspace_id=g.workspace_id, id=str(identifier or '')).first()
    if not row:
        raise APIError('Perfil do Instagram não encontrado nesta conta.', 404)
    if not instagram.usable(row):
        raise APIError('Este perfil do Instagram precisa ser reconectado no Antares.', 409)
    return row


# ---------- tools ----------
def get_account(args):
    workspace = db.session.get(Workspace, g.workspace_id)
    whatsapp = WhatsAppConnection.query.filter_by(workspace_id=g.workspace_id).first()
    return {
        'account': workspace.name,
        'acting_as': g.user.name,
        'role': g.role,
        'scopes': g.api_token.scopes,
        'token_expires_at': iso(g.api_token.expires_at),
        'whatsapp_connected': bool(whatsapp and whatsapp.state == 'open'),
        'instagram_accounts': [
            {'id': row.id, 'username': row.username, 'connected': instagram.usable(row)}
            for row in InstagramConnection.query.filter_by(workspace_id=g.workspace_id, active=True)
        ],
    }


def list_conversations(args):
    need('messages:read')
    items = inbox.list_threads(account())['items']
    channel, status, text = args.get('channel'), args.get('status'), str(args.get('query') or '').lower().strip()
    rows = []
    for item in items:
        if channel and item.get('channel') != channel:
            continue
        if status and item.get('status') != status:
            continue
        if args.get('unread_only') and not item.get('unread_count'):
            continue
        name = item.get('contact_name') or item.get('display_address') or item.get('address')
        if (
            text
            and text not in ' '.join(str(v or '') for v in (name, item.get('preview'), item.get('address'))).lower()
        ):
            continue
        rows.append(
            {
                'conversation_id': item['id'],
                'source': item['source'],
                'channel': item['channel'],
                'name': name,
                'address': item.get('display_address') if item['channel'] == 'instagram' else item.get('address'),
                'instagram_account': item.get('instagram_account'),
                'preview': item.get('preview'),
                'last_direction': item.get('last_direction'),
                'last_message_at': item.get('last_message_at'),
                'last_inbound_at': item.get('last_inbound_at'),
                'unread_count': item.get('unread_count') or 0,
                'status': item.get('status'),
            }
        )
    limit = clamp(args.get('limit'), 1, 50, 20)
    return {'conversations': rows[:limit], 'total': len(rows)}


def read_conversation(args):
    need('messages:read')
    source, limit = args.get('source'), clamp(args.get('limit'), 1, 100, 30)
    ctx = account()
    if source == 'whatsapp':
        thread = ctx.get(WhatsAppConversation, args.get('conversation_id'))
        rows = (
            ctx.query(WhatsAppMessage)
            .filter_by(conversation_id=thread.id)
            .order_by(WhatsAppMessage.occurred_at.desc(), WhatsAppMessage.created_at.desc())
            .limit(limit)
            .all()
        )
        messages = [
            {
                'direction': row.direction,
                'text': row.content,
                'kind': row.kind,
                'status': row.status,
                'at': iso(row.occurred_at),
                **({'attachment': row.filename or row.mimetype} if row.kind != 'text' else {}),
            }
            for row in rows
        ]
        header = {'channel': 'whatsapp', 'name': thread.contact_name, 'address': thread.phone}
    elif source == 'inbox':
        thread = ctx.get(InboxThread, args.get('conversation_id'))
        rows = (
            ctx.query(InboxMessage)
            .filter_by(thread_id=thread.id)
            .order_by(InboxMessage.created_at.desc())
            .limit(limit)
            .all()
        )
        messages = [
            {'direction': row.direction, 'text': row.content, 'status': row.status, 'at': iso(row.created_at)}
            for row in rows
        ]
        header = {'channel': thread.channel, 'address': thread.address if thread.channel != 'instagram' else None}
        if thread.channel == 'instagram':
            last_in = next((row.created_at for row in rows if row.direction == 'in'), None)
            header['reply_window_open'] = bool(last_in and last_in > now() - timedelta(hours=24))
    else:
        raise APIError('Informe source "whatsapp" ou "inbox", como em list_conversations.', 422)
    return {**header, 'status': thread.status, 'messages': list(reversed(messages))}


def send_message(args):
    need('messages:send')
    source, text = args.get('source'), str(args.get('text') or '').strip()
    if args.get('confirm') is not True:
        raise APIError('Mostre a mensagem à pessoa e repita com confirm=true depois da aprovação.', 422)
    if not text:
        raise APIError('Escreva o texto da mensagem.', 422)
    supplied = str(args.get('idempotency_key') or '')[:100]
    # Same key, same message: a client retry never sends twice.
    key = str(uuid.uuid5(uuid.NAMESPACE_URL, g.api_token.id + ':' + supplied)) if supplied else str(uuid.uuid4())
    ctx = account()
    if source == 'whatsapp':
        conversation = messaging.whatsapp_target(ctx, args.get('conversation_id'))
        act('send_message', {'source': source, 'conversation_id': conversation.id})
        row, _created = messaging.send_whatsapp(ctx, conversation, text, key)
        return {'message_id': row.id, 'status': row.status, 'error': row.error}
    if source == 'inbox':
        thread = ctx.get(InboxThread, args.get('conversation_id'))
        act('send_message', {'source': source, 'conversation_id': thread.id, 'channel': thread.channel})
        row, status = messaging.send_inbox_reply(ctx, thread.id, {'content': text, 'idempotency_key': key})
        db.session.commit()
        return {'message_id': row.id, 'status': row.status, 'queued': status == 202, 'error': row.error}
    raise APIError('Informe source "whatsapp" ou "inbox", como em list_conversations.', 422)


def list_instagram_accounts(args):
    need('instagram:read')
    rows = InstagramConnection.query.filter_by(workspace_id=g.workspace_id, active=True).all()
    return {
        'accounts': [
            {
                'id': row.id,
                'username': row.username,
                'name': row.name,
                'connected': instagram.usable(row),
                'can_publish': row.to_dict()['can_publish'],
                'can_read_insights': row.to_dict()['can_read_insights'],
            }
            for row in rows
        ]
    }


def get_instagram_insights(args):
    need('instagram:read')
    row = instagram_account(args.get('account_id'))
    days = clamp(args.get('days'), 1, 30, 30)
    snapshot = insights.snapshot(row, 7 if days <= 7 else 30, force=bool(args.get('refresh')))
    db.session.commit()
    data = insights.public(snapshot, row)
    data['media'] = data.get('media', [])[:12]
    return data


def list_instagram_posts(args):
    need('instagram:read')
    q = InstagramPost.query.filter_by(workspace_id=g.workspace_id)
    if args.get('account_id'):
        q = q.filter_by(connection_id=instagram_account(args['account_id']).id)
    if args.get('status'):
        q = q.filter_by(status=args['status'])
    rows = q.order_by(InstagramPost.created_at.desc()).limit(clamp(args.get('limit'), 1, 50, 20)).all()
    return {'posts': [publishing.public_post(row) for row in rows]}


def create_instagram_post(args):
    action = args.get('action') or 'draft'
    if action not in ('draft', 'schedule', 'publish'):
        raise APIError('action deve ser draft, schedule ou publish.', 422)
    if action == 'draft':
        if not {'instagram:drafts', 'instagram:publish'} & set(g.api_token.scopes or []):
            raise APIError('Este token não tem a permissão instagram:drafts.', 403)
    else:
        need('instagram:publish')
        if g.role not in ('owner', 'admin'):
            raise APIError('Somente proprietários e administradores publicam no Instagram.', 403)
        if args.get('confirm') is not True:
            raise APIError('Mostre a publicação à pessoa e repita com confirm=true depois da aprovação.', 422)
    connection = instagram_account(args.get('account_id'))
    when = None
    if action == 'schedule':
        try:
            when = datetime.fromisoformat(str(args.get('scheduled_at') or '').replace('Z', '+00:00'))
        except ValueError:
            raise APIError('scheduled_at deve ser uma data ISO 8601 com fuso horário.', 422) from None
        if when.tzinfo is None:
            raise APIError('scheduled_at precisa de fuso horário, por exemplo 2026-11-20T18:00:00-04:00.', 422)
        when = when.astimezone(timezone.utc)
    post = InstagramPost(workspace_id=g.workspace_id, created_by_id=g.user.id, status='draft', items=[], containers={})
    publishing.apply(
        post,
        {
            'connection_id': connection.id,
            'media_type': args.get('media_type'),
            'caption': args.get('caption') or '',
            'items': [
                {'url': item.get('url'), 'kind': item.get('kind')}
                for item in (args.get('media') or [])
                if isinstance(item, dict)
            ],
            'scheduled_at': when,
        },
        g.workspace_id,
    )
    if action != 'draft':
        act('create_instagram_post', {'action': action, 'connection_id': connection.id})
        publishing.schedule(post, when)
    db.session.add(post)
    db.session.flush()
    audit('instagram.post.' + action, post, {'connection_id': connection.id, 'via': 'mcp'})
    db.session.commit()
    return {
        'post': publishing.public_post(post),
        'note': 'O Antares publica em segundos; consulte list_instagram_posts para ver o resultado.'
        if action == 'publish'
        else None,
    }


def list_instagram_comments(args):
    need('instagram:read')
    connection = instagram_account(args.get('account_id'))
    token = instagram.token(connection)
    limit = clamp(args.get('limit'), 1, 50, 25)
    fields = 'id,text,timestamp,username,like_count,replies{id,text,username,timestamp}'
    if args.get('media_id'):
        media = [{'id': str(args['media_id'])}]
    else:
        data = instagram_client.graph(
            connection.instagram_id + '/media',
            token,
            params={'fields': 'id,caption,comments_count,permalink', 'limit': 10},
        )
        media = [m for m in data.get('data') or [] if m.get('comments_count')]
    found = []
    for item in media:
        data = instagram_client.graph(item['id'] + '/comments', token, params={'fields': fields, 'limit': 25})
        for comment in data.get('data') or []:
            replies = (comment.get('replies') or {}).get('data') or []
            found.append(
                {
                    'comment_id': comment.get('id'),
                    'media_id': item['id'],
                    'post_caption': (item.get('caption') or '')[:120] or None,
                    'post_link': item.get('permalink'),
                    'username': comment.get('username'),
                    'text': comment.get('text'),
                    'at': comment.get('timestamp'),
                    'likes': comment.get('like_count'),
                    'answered_by_account': any(r.get('username') == connection.username for r in replies),
                    'replies': [{'username': r.get('username'), 'text': r.get('text')} for r in replies[:5]],
                }
            )
    stored = {
        row.comment_id: row
        for row in InstagramComment.query.filter(
            InstagramComment.connection_id == connection.id,
            InstagramComment.comment_id.in_([c['comment_id'] for c in found] or ['']),
        )
    }
    for comment in found:
        row = stored.get(comment['comment_id'])
        comment['replied_publicly'] = bool(row and row.replied_at) or comment['answered_by_account']
        comment['replied_privately'] = bool(row and row.private_replied_at)
        comment.pop('answered_by_account')
    if args.get('unanswered_only'):
        found = [c for c in found if not c['replied_publicly'] and not c['replied_privately']]
    found.sort(key=lambda c: c.get('at') or '', reverse=True)
    return {'comments': found[:limit]}


def reply_instagram_comment(args):
    need('instagram:comments')
    if args.get('confirm') is not True:
        raise APIError('Mostre a resposta à pessoa e repita com confirm=true depois da aprovação.', 422)
    connection = instagram_account(args.get('account_id'))
    text = str(args.get('text') or '').strip()
    if not text:
        raise APIError('Escreva o texto da resposta.', 422)
    private = bool(args.get('private'))
    act(
        'reply_instagram_comment',
        {'connection_id': connection.id, 'comment_id': str(args.get('comment_id')), 'private': private},
    )
    row = instagram_comments.manual_reply(connection, args.get('comment_id'), text, private)
    db.session.commit()
    return {'replied': True, 'private': private, 'comment_id': row.comment_id}


def tool(name, title, description, handler, properties, required=(), hints=READ):
    return name, {
        'handler': handler,
        'spec': {
            'name': name,
            'title': title,
            'description': description,
            'inputSchema': {
                'type': 'object',
                'properties': properties,
                'required': list(required),
                'additionalProperties': False,
            },
            'annotations': {'title': title, **hints},
        },
    }


SOURCE = {'type': 'string', 'enum': ['whatsapp', 'inbox'], 'description': 'Campo source de list_conversations.'}
TOOLS = dict(
    [
        tool(
            'get_account',
            'Conta e permissões',
            'Conta do Antares, permissões do token e canais conectados.',
            get_account,
            {},
        ),
        tool(
            'list_conversations',
            'Listar conversas',
            'Conversas da caixa de entrada (WhatsApp, Instagram, e-mail, SMS), mais recentes primeiro.',
            list_conversations,
            {
                'channel': {'type': 'string', 'enum': ['whatsapp', 'instagram', 'email', 'sms']},
                'status': {'type': 'string', 'enum': ['open', 'closed']},
                'unread_only': {'type': 'boolean'},
                'query': {'type': 'string', 'description': 'Filtra por nome, endereço ou última mensagem.'},
                'limit': {'type': 'integer', 'minimum': 1, 'maximum': 50},
            },
        ),
        tool(
            'read_conversation',
            'Ler conversa',
            'Mensagens de uma conversa em ordem cronológica. No Instagram informa se a janela de 24 h está aberta.',
            read_conversation,
            {
                'conversation_id': {'type': 'string'},
                'source': SOURCE,
                'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100},
            },
            ('conversation_id', 'source'),
        ),
        tool(
            'send_message',
            'Enviar mensagem',
            'Responde uma conversa pelo canal dela. Irreversível: peça aprovação e envie confirm=true. '
            'Use idempotency_key para que uma repetição não envie duas vezes.',
            send_message,
            {
                'conversation_id': {'type': 'string'},
                'source': SOURCE,
                'text': {'type': 'string', 'maxLength': 4000},
                'idempotency_key': {'type': 'string', 'maxLength': 100},
                'confirm': CONFIRM,
            },
            ('conversation_id', 'source', 'text', 'confirm'),
            ACT,
        ),
        tool(
            'list_instagram_accounts',
            'Perfis do Instagram',
            'Perfis conectados e o que cada um pode fazer.',
            list_instagram_accounts,
            {},
        ),
        tool(
            'get_instagram_insights',
            'Métricas do Instagram',
            'Seguidores, alcance, visualizações, interações, público e publicações recentes (7 ou 30 dias).',
            get_instagram_insights,
            {'account_id': ACCOUNT, 'days': {'type': 'integer', 'enum': [7, 30]}, 'refresh': {'type': 'boolean'}},
            ('account_id',),
        ),
        tool(
            'list_instagram_posts',
            'Publicações do Antares',
            'Rascunhos, agendadas e publicadas pelo Antares, com situação e link.',
            list_instagram_posts,
            {
                'account_id': ACCOUNT,
                'status': {
                    'type': 'string',
                    'enum': ['draft', 'scheduled', 'processing', 'publishing', 'published', 'failed', 'unknown'],
                },
                'limit': {'type': 'integer', 'minimum': 1, 'maximum': 50},
            },
        ),
        tool(
            'create_instagram_post',
            'Criar publicação',
            'Cria rascunho, agenda ou publica imagem (JPEG), carrossel (2 a 10) ou Reel a partir de links HTTPS públicos. '
            'schedule e publish são irreversíveis: peça aprovação e envie confirm=true.',
            create_instagram_post,
            {
                'account_id': ACCOUNT,
                'media_type': {'type': 'string', 'enum': ['IMAGE', 'CAROUSEL', 'REELS']},
                'caption': {'type': 'string', 'maxLength': 2200},
                'media': {
                    'type': 'array',
                    'minItems': 1,
                    'maxItems': 10,
                    'items': {
                        'type': 'object',
                        'properties': {
                            'url': {'type': 'string'},
                            'kind': {'type': 'string', 'enum': ['image', 'video']},
                        },
                        'required': ['url', 'kind'],
                        'additionalProperties': False,
                    },
                },
                'action': {'type': 'string', 'enum': ['draft', 'schedule', 'publish']},
                'scheduled_at': {'type': 'string', 'description': 'ISO 8601 com fuso, para action=schedule.'},
                'confirm': {'type': 'boolean', 'description': 'Obrigatório (true) para schedule e publish.'},
            },
            ('account_id', 'media_type', 'media'),
            ACT,
        ),
        tool(
            'list_instagram_comments',
            'Comentários do Instagram',
            'Comentários das publicações recentes (ou de uma publicação), com indicação de já respondidos.',
            list_instagram_comments,
            {
                'account_id': ACCOUNT,
                'media_id': {'type': 'string'},
                'unanswered_only': {'type': 'boolean'},
                'limit': {'type': 'integer', 'minimum': 1, 'maximum': 50},
            },
            ('account_id',),
        ),
        tool(
            'reply_instagram_comment',
            'Responder comentário',
            'Responde um comentário publicamente ou por mensagem privada (private=true, até 7 dias após o comentário). '
            'Uma resposta de cada tipo por comentário. Irreversível: peça aprovação e envie confirm=true.',
            reply_instagram_comment,
            {
                'account_id': ACCOUNT,
                'comment_id': {'type': 'string'},
                'text': {'type': 'string', 'maxLength': 1000},
                'private': {'type': 'boolean'},
                'confirm': CONFIRM,
            },
            ('account_id', 'comment_id', 'text', 'confirm'),
            ACT,
        ),
    ]
)


def visible_tools():
    """Tools this token can use; the AI never sees actions it cannot take."""
    scopes = set(g.api_token.scopes or [])
    needs = {
        'list_conversations': {'messages:read'},
        'read_conversation': {'messages:read'},
        'send_message': {'messages:send'},
        'list_instagram_accounts': {'instagram:read'},
        'get_instagram_insights': {'instagram:read'},
        'list_instagram_posts': {'instagram:read'},
        'create_instagram_post': {'instagram:drafts', 'instagram:publish'},
        'list_instagram_comments': {'instagram:read'},
        'reply_instagram_comment': {'instagram:comments'},
    }
    return [entry['spec'] for name, entry in TOOLS.items() if name not in needs or needs[name] & scopes]
