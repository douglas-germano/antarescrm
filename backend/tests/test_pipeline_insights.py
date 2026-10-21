import pytest
from flask_jwt_extended import create_access_token
from app import create_app
from app.extensions import db
from app.models import Workspace, User, PipelineStage, Opportunity, StageHistory


@pytest.fixture()
def ctx():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SQLALCHEMY_ENGINE_OPTIONS': {},
                      'JWT_SECRET_KEY': 'test-only-key-with-more-than-thirty-two-characters', 'RATELIMIT_ENABLED': False})
    with app.app_context():
        db.create_all()
        workspace = Workspace(name='W', slug='insights-test')
        db.session.add(workspace); db.session.flush()
        user = User(workspace_id=workspace.id, name='A', email='a@example.invalid', role='owner', password_hash='x')
        stage = PipelineStage(workspace_id=workspace.id, name='Novo', position=0)
        db.session.add_all([user, stage]); db.session.flush()
        deal = Opportunity(workspace_id=workspace.id, stage_id=stage.id, owner_id=user.id, title='Negócio', amount=100)
        db.session.add(deal); db.session.flush()
        db.session.add(StageHistory(workspace_id=workspace.id, opportunity_id=deal.id, to_stage_id=stage.id, user_id=user.id))
        db.session.commit()
        token = create_access_token(identity=user.id, additional_claims={'ver': 0})
        yield app.test_client(), {'Authorization': 'Bearer ' + token}, stage
        db.session.remove(); db.drop_all()


def test_stage_probability_roundtrip_and_bounds(ctx):
    client, headers, stage = ctx
    ok = client.patch(f'/api/v1/pipeline/stages/{stage.id}', json={'probability': 40}, headers=headers)
    assert ok.status_code == 200 and ok.get_json()['probability'] == 40
    assert client.patch(f'/api/v1/pipeline/stages/{stage.id}', json={'probability': 120}, headers=headers).status_code == 422


def test_listed_deals_carry_stage_age_and_last_contact(ctx):
    client, headers, _ = ctx
    item = client.get('/api/v1/opportunities?status=open', headers=headers).get_json()['items'][0]
    assert item['stage_changed_at'] and item['last_contact_at'] is None
