"""Real PostgreSQL lock regression; disposable database only."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from app.extensions import db
from app.models import HistorySync, WhatsAppMessage
from app.services import history, whatsapp
from helpers.whatsapp import raw

pytestmark = pytest.mark.skipif(
    not os.environ.get('ANTARES_POSTGRES_TEST_URL'), reason='Disposable PostgreSQL database required'
)


def test_two_workers_do_not_process_the_same_history_batch(pg, monkeypatch):
    app, workspace_id, _, _ = pg
    with app.app_context():
        connection = whatsapp.connection_for(workspace_id)
        job = HistorySync(
            workspace_id=workspace_id,
            channel='whatsapp',
            connection_id=connection.id,
            identity=connection.instance_name,
            status='queued',
            phase='messages',
            cursor={'page': 1, 'mappings': {}},
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id
    entered, release = Event(), Event()

    def page(connection, number):
        if number == 1:
            entered.set()
            assert release.wait(10)
            return [raw('postgres-history')], 1
        return [], 1

    monkeypatch.setattr(history, 'messages_page', page)

    def work():
        with app.app_context():
            return history.process(limit=100)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(work)
        try:
            assert entered.wait(10)
            second = pool.submit(work)
            assert second.result(timeout=5) == 0
        finally:
            release.set()
        assert first.result(timeout=10) == 1
    with app.app_context():
        assert WhatsAppMessage.query.filter_by(workspace_id=workspace_id).count() == 1
        assert db.session.get(HistorySync, job_id).imported == 1
