import pytest

pytest.skip("Copiloto de Pesca desativado", allow_module_level=True)

"""Real transactional limits: simultaneous reviews and worker budget reservations."""

from concurrent.futures import ThreadPoolExecutor

from app.extensions import db
from app.models import FishingDraft, FishingPost, FishingSettings, FishingUsage
from app.services import fishing
from flask_jwt_extended import create_access_token


def test_two_simultaneous_reviews_share_one_daily_slot(pg):
    app, workspace_id, _, user_id = pg
    db.session.add(FishingSettings(workspace_id=workspace_id, enabled=True, daily_limit=1))
    body = []
    for index in range(2):
        row = FishingPost(
            workspace_id=workspace_id,
            media_id=f'review{index}',
            url=f'https://www.instagram.com/p/review{index}/',
            caption='Cozinha de madeira.',
            status='na_fila',
        )
        db.session.add(row)
        db.session.flush()
        draft = FishingDraft(
            workspace_id=workspace_id,
            post_id=row.id,
            kind='pergunta',
            text='Como escolheram essa madeira para a bancada?',
            generation=1,
        )
        db.session.add(draft)
        db.session.flush()
        body.append((row.id, {'draft_id': draft.id, 'text': draft.text}))
    db.session.commit()
    token = create_access_token(identity=user_id, additional_claims={'ver': 0})

    def review(item):
        post_id, data = item
        with app.test_client() as client:
            return client.post(
                f'/api/v1/fishing/posts/{post_id}/open', json=data, headers={'Authorization': 'Bearer ' + token}
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(review, body))
    assert sorted(statuses) == [200, 409]
    assert (
        FishingPost.query.filter_by(workspace_id=workspace_id, status='na_fila')
        .filter(FishingPost.opened_at.is_not(None))
        .count()
        == 1
    )


def test_workers_cannot_exceed_shared_ai_budget(pg, monkeypatch):
    app, workspace_id, _, _ = pg
    app.config.update(OPENROUTER_API_KEY='test-only', FISHING_TRIAGE_MODEL='test/fast', FISHING_DRAFT_MODEL='test/main')
    db.session.add(FishingSettings(workspace_id=workspace_id, enabled=True, daily_ai_limit=1))
    for index in range(2):
        db.session.add(
            FishingPost(
                workspace_id=workspace_id,
                media_id=f'worker{index}',
                url=f'https://www.instagram.com/p/worker{index}/',
                caption='Cozinha com bancada de madeira.',
            )
        )
    db.session.commit()
    calls = []

    def complete(*args, **kwargs):
        calls.append(True)
        return {
            'choices': [{'finish_reason': 'stop', 'message': {'content': '{"nota":85,"motivo":"Relevante."}'}}],
            'usage': {'total_tokens': 25, 'cost': 0.001},
        }

    monkeypatch.setattr(fishing.ai, 'complete', complete)

    def run(_):
        with app.app_context():
            try:
                return fishing.process(limit=1)
            finally:
                db.session.remove()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, range(2)))
    assert len(calls) == 1
    assert FishingUsage.query.filter_by(workspace_id=workspace_id).count() == 1
