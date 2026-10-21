"""Optional PostgreSQL concurrency and FK checks, restricted to disposable test databases."""

import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from urllib.parse import urlparse
import pytest
from flask_migrate import upgrade
from flask_jwt_extended import create_access_token
from app import create_app
from app.extensions import db
from app.models import (
    Workspace,
    User,
    LeadForm,
    PipelineStage,
    AutomationRule,
    Contact,
    Opportunity,
    Task,
    FormSubmission,
    AutomationRun,
)

URI = os.getenv('ANTARES_POSTGRES_TEST_URL')
pytestmark = pytest.mark.skipif(
    not URI, reason='Set ANTARES_POSTGRES_TEST_URL to a disposable antares_test_* database.'
)


@pytest.fixture()
def pg():
    assert urlparse(URI).path.lstrip('/').startswith('antares_test_'), 'Refusing a non-test database'
    app = create_app(
        {
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': URI,
            'RATELIMIT_ENABLED': False,
            'JWT_SECRET_KEY': 'postgres-test-only-key-longer-than-thirty-two-characters',
        }
    )
    with app.app_context():
        upgrade(directory=str(Path(__file__).resolve().parents[1] / 'migrations'))
        ws = Workspace(name='Concurrency fixture', slug='fixture-' + str(uuid4()))
        db.session.add(ws)
        db.session.flush()
        user = User(workspace_id=ws.id, name='Test', email='test@example.com', role='owner', password_hash='unused')
        stage = PipelineStage(workspace_id=ws.id, name='New', position=0)
        db.session.add_all([user, stage])
        db.session.flush()
        form = LeadForm(workspace_id=ws.id, name='Test', headline='Test', stage_id=stage.id, active=True)
        rule = AutomationRule(
            workspace_id=ws.id, name='Rule', event='form.submitted', task_title='Call lead', active=True
        )
        db.session.add_all([form, rule])
        db.session.commit()
        yield app, ws.id, form.id, user.id
        db.session.remove()
        db.engine.dispose()


def test_concurrent_retries_create_exactly_one_submission_and_task(pg):
    app, workspace_id, form_id, _ = pg
    key = str(uuid4())
    barrier = Barrier(2)

    def submit():
        with app.test_client() as client:
            barrier.wait(timeout=10)
            return client.post(
                f'/api/v1/public/forms/{form_id}/submit',
                json={
                    'submission_key': key,
                    'name': 'Concurrency lead',
                    'email': 'concurrency@example.com',
                    'consent': True,
                },
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert results == [200, 200]
    for model in [Contact, Opportunity, Task, FormSubmission, AutomationRun]:
        assert model.query.filter_by(workspace_id=workspace_id).count() == 1


def test_task_deletion_preserves_automation_history(pg):
    app, workspace_id, form_id, user_id = pg
    with app.test_client() as client:
        assert (
            client.post(
                f'/api/v1/public/forms/{form_id}/submit',
                json={
                    'submission_key': str(uuid4()),
                    'name': 'Delete test',
                    'email': 'delete@example.com',
                    'consent': True,
                },
            ).status_code
            == 200
        )
        task = Task.query.filter_by(workspace_id=workspace_id).one()
        task_id = task.id
        token = create_access_token(identity=user_id, additional_claims={'ver': 0})
        assert (
            client.delete('/api/v1/tasks/' + task_id, headers={'Authorization': 'Bearer ' + token}).status_code == 204
        )
        db.session.expire_all()
        assert AutomationRun.query.filter_by(workspace_id=workspace_id).one().task_id is None


def test_concurrent_distinct_submissions_reuse_contact_across_forms(pg):
    app, workspace_id, form_id, _ = pg
    original = db.session.get(LeadForm, form_id)
    other = LeadForm(
        workspace_id=workspace_id, name='Second', headline='Second', stage_id=original.stage_id, active=True
    )
    db.session.add(other)
    db.session.commit()
    other_id = other.id
    barrier = Barrier(4)

    def submit(index):
        with app.test_client() as client:
            barrier.wait(timeout=10)
            return client.post(
                f'/api/v1/public/forms/{form_id if index % 2 else other_id}/submit',
                json={
                    'submission_key': str(uuid4()),
                    'name': 'Same lead',
                    'email': 'same@example.com',
                    'consent': True,
                },
            ).status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(submit, range(4)))
    assert results == [200] * 4
    assert Contact.query.filter_by(workspace_id=workspace_id).count() == 1
    assert FormSubmission.query.filter_by(workspace_id=workspace_id).count() == 4
    assert Opportunity.query.filter_by(workspace_id=workspace_id).count() == 4


def test_concurrent_booking_across_calendars_reserves_one_slot(pg, monkeypatch):
    from datetime import datetime, timezone
    from app.models import BookingCalendar, Booking
    from app.services import booking

    app, workspace_id, _, user_id = pg
    monkeypatch.setattr(booking, 'now', lambda: datetime(2030, 1, 7, 12, tzinfo=timezone.utc))
    calendar_ids = []
    for name in ['One', 'Two']:
        row = BookingCalendar(
            workspace_id=workspace_id,
            name=name,
            assignee_id=user_id,
            active=True,
            lead_minutes=0,
            availability={str(i): [{'start': '09:00', 'end': '18:00'}] for i in range(7)},
        )
        db.session.add(row)
        db.session.flush()
        calendar_ids.append(row.id)
    db.session.commit()
    barrier = Barrier(2)

    def reserve(calendar_id):
        with app.test_client() as client:
            barrier.wait(timeout=10)
            return client.post(
                '/api/v1/public/calendars/' + calendar_id + '/book',
                json={
                    'submission_key': str(uuid4()),
                    'name': 'Booking lead',
                    'email': 'booking@example.test',
                    'starts_at': '2030-01-08T13:00:00+00:00',
                    'consent': True,
                },
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, calendar_ids))
    assert sorted(results) == [200, 409]
    assert Booking.query.filter_by(workspace_id=workspace_id).count() == 1


def test_monthly_report_groups_sales_using_account_timezone(pg, monkeypatch):
    from datetime import datetime, date, timezone
    from app.models import PipelineStage

    app, workspace_id, _, user_id = pg
    monkeypatch.setattr('app.routes.reports.today', lambda: date(2030, 2, 15))
    stage = PipelineStage.query.filter_by(workspace_id=workspace_id).first()
    deal = Opportunity(
        workspace_id=workspace_id,
        title='UTC boundary',
        stage_id=stage.id,
        status='won',
        amount=100,
        closed_at=datetime(2030, 1, 1, 2, tzinfo=timezone.utc),
    )
    db.session.add(deal)
    db.session.commit()
    token = create_access_token(identity=user_id, additional_claims={'ver': 0})
    with app.test_client() as client:
        response = client.get('/api/v1/reports/won-by-month', headers={'Authorization': 'Bearer ' + token})
    assert response.status_code == 200, response.json
    assert response.json['items'] == [{'month': '2029-12', 'count': 1, 'amount': '100.00'}]
