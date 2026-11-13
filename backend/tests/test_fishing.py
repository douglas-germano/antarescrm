import pytest

pytest.skip("Copiloto de Pesca desativado", allow_module_level=True)

"""Copilot behavior with deterministic providers; never sends real comments or AI requests."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
import requests
from app.common import APIError
from app.extensions import db
from app.models import FishingDraft, FishingPost, FishingSettings, FishingUsage, now
from app.services import fishing
from app.services.fishing import ai

SETTINGS = {
    'enabled': True,
    'brand_name': 'Oficina',
    'brand_profile': 'Móveis sob medida para famílias.',
    'tone': 'Próximo, curioso, objetivo',
    'own_username': 'oficina',
    'daily_limit': 40,
    'daily_ai_limit': 100,
    'forbidden_words': ['imperdível'],
}
OPTIONS = [
    {'tipo': 'acrescenta', 'texto': 'Nesse armário, deixar a gaveta dos talheres perto da bancada facilita o preparo.'},
    {'tipo': 'pergunta', 'texto': 'Qual foi o desafio para encaixar essa bancada de madeira no espaço?'},
    {'tipo': 'reacao', 'texto': 'O contraste entre a madeira e os azulejos deu profundidade à cozinha.'},
]


@pytest.fixture()
def ready(env, monkeypatch):
    client, data = env
    client.application.config.update(
        OPENROUTER_API_KEY='secret-test-key', FISHING_TRIAGE_MODEL='test/fast', FISHING_DRAFT_MODEL='test/main'
    )
    assert client.patch('/api/v1/fishing/settings', json=SETTINGS, headers=data['headers']()).status_code == 200
    calls = []

    def complete(phase, model, context, image=None):
        calls.append((phase, context))
        value = (
            {'nota': 85, 'motivo': 'Assunto pertinente ao público da marca.'}
            if phase == 'triage'
            else {'pular': False, 'resumo_do_post': 'Cozinha com armários e bancada de madeira.', 'opcoes': OPTIONS}
        )
        return {
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(value)}}],
            'usage': {'total_tokens': 123, 'cost': 0.00015},
        }

    monkeypatch.setattr(ai, 'complete', complete)
    return client, data, calls


def add(client, data, code='post1', **extra):
    return client.post(
        '/api/v1/fishing/posts',
        json={
            'url': f'https://www.instagram.com/p/{code}/?utm_source=share',
            'caption': 'Cozinha com bancada de madeira e armário funcional.',
            'author': '@arquiteta',
            **extra,
        },
        headers=data['headers'](),
    )


def queued(client, data):
    response = add(client, data)
    assert response.status_code == 201, response.json
    assert fishing.process() == 1
    rows = client.get('/api/v1/fishing/posts', headers=data['headers']()).json['items']
    assert len(rows) == 1
    return rows[0]


def test_defaults_permissions_and_no_provider(env):
    client, data = env
    assert client.get('/api/v1/fishing/settings').status_code == 401
    settings = client.get('/api/v1/fishing/settings', headers=data['headers']()).json
    assert settings['enabled'] is False and settings['provider_ready'] is False
    assert settings['daily_limit'] == 40
    assert (
        client.patch('/api/v1/fishing/settings', json=SETTINGS, headers=data['headers'](data['member'])).status_code
        == 403
    )
    assert add(client, data).status_code == 422
    assert fishing.process() == 0


def test_full_review_publish_undo_and_metrics(ready):
    client, data, calls = ready
    row = queued(client, data)
    assert row['score'] == 85 and len(row['drafts']) == 3
    assert 'image_data' not in row
    assert [call[0] for call in calls] == ['triage', 'draft']
    assert 'contacts' not in calls[0][1]
    draft = row['drafts'][0]
    text = draft['text'] + ' Boa solução.'
    prefix = '/api/v1/fishing/posts/' + row['id']
    assert client.post(prefix + '/decide', json={'action': 'publicado'}, headers=data['headers']()).status_code == 409
    response = client.post(prefix + '/open', json={'draft_id': draft['id'], 'text': text}, headers=data['headers']())
    assert response.status_code == 200, response.json
    assert response.json['post']['status'] == 'na_fila'
    assert client.post(prefix + '/regenerate', headers=data['headers']()).status_code == 409
    assert (
        client.post(
            prefix + '/open', json={'draft_id': draft['id'], 'text': text}, headers=data['headers']()
        ).status_code
        == 409
    )
    assert client.post(prefix + '/decide', json={'action': 'publicado'}, headers=data['headers']()).status_code == 200
    metrics = client.get('/api/v1/fishing/metrics', headers=data['headers']()).json
    assert metrics['published_today'] == 1 and metrics['edit_rate'] == 100 and metrics['tokens'] == 246
    assert Decimal(metrics['cost_usd']) == Decimal('.00030') and metrics['unknown_cost_calls'] == 0
    assert client.post(prefix + '/decide', json={'action': 'publicado'}, headers=data['headers']()).status_code == 409
    assert client.post(prefix + '/decide', json={'action': 'desfazer'}, headers=data['headers']()).status_code == 200
    assert FishingPost.query.one().status == 'pulado'


def test_tenant_scope_and_publication_owner(ready):
    client, data, _ = ready
    row = queued(client, data)
    outsider = data['headers'](data['outsider'])
    assert client.get('/api/v1/fishing/posts?status=todos', headers=outsider).json['total'] == 0
    assert client.get('/api/v1/fishing/metrics', headers=outsider).json['total'] == 0
    assert client.get('/api/v1/fishing/posts/' + row['id'] + '/image', headers=outsider).status_code == 404
    for action in ('open', 'regenerate', 'decide'):
        assert client.post(f'/api/v1/fishing/posts/{row["id"]}/{action}', json={}, headers=outsider).status_code == 404
    client.post(
        f'/api/v1/fishing/posts/{row["id"]}/open',
        json={'draft_id': row['drafts'][0]['id'], 'text': row['drafts'][0]['text']},
        headers=data['headers'](),
    )
    response = client.post(
        f'/api/v1/fishing/posts/{row["id"]}/decide',
        json={'action': 'publicado'},
        headers=data['headers'](data['member']),
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    'url',
    [
        'http://instagram.com/p/abc',
        'https://instagram.com.evil.test/p/abc',
        'https://u:p@instagram.com/p/abc',
        'https://127.0.0.1/p/abc',
        'javascript:alert(1)',
        'https://instagram.com/profile',
    ],
)
def test_links_are_canonical_and_never_fetched(ready, url):
    client, data, calls = ready
    assert add(client, data, url=url).status_code == 422
    assert not calls


def test_duplicate_blocked_author_and_image_validation(ready):
    client, data, _ = ready
    response = add(client, data)
    assert response.json['url'] == 'https://www.instagram.com/p/post1/'
    assert add(client, data).status_code == 409
    assert add(client, data, 'own', author='@oficina').status_code == 422
    assert add(client, data, 'image', image_data='data:image/png;base64,YWJj').status_code == 422
    assert client.get('/api/v1/fishing/posts?status=invalid', headers=data['headers']()).status_code == 422


def test_daily_and_author_limits_include_open_reservations(ready):
    client, data, _ = ready
    row = queued(client, data)
    config = FishingSettings.query.one()
    config.daily_limit = 1
    db.session.commit()
    open_body = {'draft_id': row['drafts'][0]['id'], 'text': row['drafts'][0]['text']}
    assert (
        client.post(f'/api/v1/fishing/posts/{row["id"]}/open', json=open_body, headers=data['headers']()).status_code
        == 200
    )
    response = add(client, data, 'post2')
    fishing.process()
    second = db.session.get(FishingPost, response.json['id'])
    draft = FishingDraft.query.filter_by(post_id=second.id).first()
    body = {'draft_id': draft.id, 'text': draft.text}
    assert (
        client.post(f'/api/v1/fishing/posts/{second.id}/open', json=body, headers=data['headers']()).status_code == 409
    )
    config.daily_limit = 40
    db.session.commit()
    assert (
        client.post(f'/api/v1/fishing/posts/{second.id}/open', json=body, headers=data['headers']()).status_code == 409
    )


def test_regeneration_preserves_history_and_rejects_old_draft(ready):
    client, data, _ = ready
    row = queued(client, data)
    assert client.post(f'/api/v1/fishing/posts/{row["id"]}/regenerate', headers=data['headers']()).status_code == 200
    assert fishing.process() == 1
    assert FishingDraft.query.count() == 6
    assert (
        client.post(
            f'/api/v1/fishing/posts/{row["id"]}/open',
            json={'draft_id': row['drafts'][0]['id'], 'text': row['drafts'][0]['text']},
            headers=data['headers'](),
        ).status_code
        == 422
    )


def test_invalid_model_output_keeps_cost_and_never_retries(ready, monkeypatch):
    client, data, calls = ready
    original = ai.complete

    def invalid(*args, **kwargs):
        body = original(*args, **kwargs)
        body['choices'][0]['message']['content'] = 'invalid'
        return body

    monkeypatch.setattr(ai, 'complete', invalid)
    add(client, data)
    assert fishing.process() == 1 and fishing.process() == 0
    assert FishingPost.query.one().status == 'erro' and FishingDraft.query.count() == 0
    assert FishingUsage.query.one().cost_usd == Decimal('.00015')
    assert len(calls) == 1


def test_low_score_and_bad_drafts_are_discarded(ready, monkeypatch):
    client, data, _ = ready
    original = ai.complete

    def low(*args, **kwargs):
        body = original(*args, **kwargs)
        body['choices'][0]['message']['content'] = json.dumps({'nota': 0, 'motivo': 'Conteúdo sensível.'})
        return body

    monkeypatch.setattr(ai, 'complete', low)
    add(client, data)
    fishing.process()
    assert FishingPost.query.one().status == 'descartado'
    assert FishingDraft.query.count() == 0 and FishingUsage.query.count() == 1
    config = FishingSettings.query.one()
    for text in (
        'Veja https://teste.com',
        'Compre #agora',
        'Oi @autor',
        'Oferta imperdível',
        'amei',
        'Custa R$ 10',
        'site exemplo.com',
    ):
        assert not fishing.valid_text(text, config, [])
    assert not fishing.valid_text(OPTIONS[0]['texto'], config, [OPTIONS[0]['texto']])


def test_ai_budget_disabled_workspace_expiration_and_stale_processing(ready):
    client, data, calls = ready
    config = FishingSettings.query.one()
    config.daily_ai_limit = 1
    db.session.commit()
    add(client, data)
    fishing.process()
    assert len(calls) == 1 and FishingPost.query.one().status == 'erro'
    config.enabled = False
    db.session.commit()
    assert (
        client.post(
            f'/api/v1/fishing/posts/{FishingPost.query.one().id}/regenerate', headers=data['headers']()
        ).status_code
        == 422
    )
    row = FishingPost.query.one()
    row.status, row.created_at = 'na_fila', now() - timedelta(hours=49)
    db.session.commit()
    client.get('/api/v1/fishing/posts', headers=data['headers']())
    db.session.refresh(row)
    assert row.status == 'expirado'
    row.status, row.created_at, row.processing_at = 'processando', now(), now() - timedelta(minutes=6)
    db.session.commit()
    fishing.process()
    db.session.refresh(row)
    assert row.status == 'erro' and len(calls) == 1


def test_adapter_contract_and_error_redaction(env, monkeypatch):
    client, _ = env
    client.application.config['OPENROUTER_API_KEY'] = 'private-key'
    calls = []

    class Response:
        status_code = 200

        def json(self):
            return {'choices': []}

    def fake(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(requests, 'post', fake)
    assert ai.complete('triage', 'test/model', {'post': 'caption'}) == {'choices': []}
    url, kwargs = calls[0]
    assert url == 'https://openrouter.ai/api/v1/chat/completions'
    assert kwargs['json']['provider']['require_parameters'] is True
    assert kwargs['json']['response_format']['json_schema']['strict'] is True
    assert 'reasoning' not in kwargs['json']
    client.application.config['FISHING_DISABLE_REASONING'] = True
    ai.complete('draft', 'nvidia/test:free', {'post': 'caption'})
    assert calls[-1][1]['json']['reasoning'] == {'enabled': False}
    assert kwargs['timeout'] == (3, 20) and kwargs['allow_redirects'] is False

    def failed(*args, **kwargs):
        raise requests.Timeout('private-key')

    monkeypatch.setattr(requests, 'post', failed)
    with pytest.raises(APIError) as error:
        ai.complete('triage', 'test/model', {})
    assert 'private-key' not in error.value.message


@pytest.mark.parametrize(
    'enabled,model,expected',
    [
        (False, 'nvidia/test:free', 'deny'),
        (True, 'nvidia/test:free', 'allow'),
        (True, 'anthropic/test', 'deny'),
    ],
)
def test_free_training_requires_explicit_config_and_never_changes_paid_policy(
    env, monkeypatch, enabled, model, expected
):
    client, _ = env
    client.application.config.update(OPENROUTER_API_KEY='test-only', FISHING_ALLOW_FREE_MODEL_TRAINING=enabled)
    seen = []

    class Response:
        status_code = 200

        def json(self):
            return {'choices': []}

    def complete(url, **kwargs):
        seen.append(kwargs['json'])
        return Response()

    monkeypatch.setattr(requests, 'post', complete)
    ai.complete('triage', model, {'post': 'Conteúdo fictício'})
    assert seen[0]['provider']['data_collection'] == expected
    assert seen[0]['provider']['require_parameters'] is True


def test_list_batches_latest_drafts_and_does_not_rewrite_cleared_images(env):
    from sqlalchemy import event

    client, data = env
    posts = []
    for number in range(4):
        post = FishingPost(
            workspace_id=data['ws'].id,
            url=f'https://instagram.com/p/{number}/',
            media_id=str(number),
            caption='Post',
            status='na_fila',
            created_at=now() - timedelta(days=3),
            image_data='image',
        )
        db.session.add(post)
        posts.append(post)
    db.session.flush()
    # Keep these recent so expiration does not alter their status.
    posts[-1].created_at = now()
    for post in posts:
        for generation in (1, 2):
            db.session.add(
                FishingDraft(
                    workspace_id=data['ws'].id,
                    post_id=post.id,
                    kind='reacao',
                    text=f'Geração {generation}',
                    generation=generation,
                )
            )
    db.session.commit()
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append((statement.lower(), cursor.rowcount))

    event.listen(db.engine, 'after_cursor_execute', record)
    try:
        response = client.get('/api/v1/fishing/posts?status=todos', headers=data['headers']())
        assert response.status_code == 200
        assert len(response.json['items']) == 4
        assert all([draft['text'] for draft in item['drafts']] == ['Geração 2'] for item in response.json['items'])
        selects = [sql for sql, _ in statements if sql.lstrip().startswith('select') and 'fishing_drafts' in sql]
        assert len(selects) == 1
        statements.clear()
        client.get('/api/v1/fishing/posts?status=todos', headers=data['headers']())
        updates = [count for sql, count in statements if sql.lstrip().startswith('update fishing_posts')]
        assert updates and all(count == 0 for count in updates)
    finally:
        event.remove(db.engine, 'after_cursor_execute', record)
