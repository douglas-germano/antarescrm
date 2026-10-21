"""Real PostgreSQL worker claims; all provider I/O is replaced by bounded test adapters."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4
from test_postgres_integration import pg, pytestmark
from app.extensions import db
from app.models import Contact, AutomationRule, AutomationJob, Task, InboxMessage
from app.services.automations import emit, process
from app.services.communications import enqueue, dispatch


def test_two_workers_do_not_skip_locked_predecessor(pg, monkeypatch):
    app, workspace_id, _, _ = pg
    rule = AutomationRule(
        workspace_id=workspace_id,
        name='Sequential',
        event='contact.created',
        active=True,
        task_title='Legacy',
        actions=[{'kind': 'create_task', 'title': 'First'}, {'kind': 'create_task', 'title': 'Second'}],
    )
    contact = Contact(workspace_id=workspace_id, name='Worker contact')
    db.session.add_all([rule, contact])
    db.session.flush()
    emit(workspace_id, 'contact.created', contact.id, contact)
    db.session.commit()
    import app.services.automations as service

    original = service.execute
    entered = Event()
    release = Event()

    def controlled(job, *args):
        if job.position == 0:
            entered.set()
            assert release.wait(timeout=10)
        return original(job, *args)

    monkeypatch.setattr(service, 'execute', controlled)

    def work():
        with app.app_context():
            return process(workspace_id, limit=1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(work)
        try:
            assert entered.wait(timeout=10)
            assert pool.submit(work).result(timeout=10) == []
        finally:
            release.set()
        assert len(first.result(timeout=10)) == 1
    assert len(process(workspace_id)) == 1
    db.session.expire_all()
    assert {row.status for row in AutomationJob.query.filter_by(workspace_id=workspace_id)} == {'completed'}
    assert Task.query.filter_by(workspace_id=workspace_id).count() == 2


def test_concurrent_dispatch_claims_one_message_once(pg, monkeypatch):
    app, workspace_id, _, user_id = pg
    app.config['COMMUNICATION_ACCOUNTS'] = {
        workspace_id: {'email': {'host': 'smtp.example.test', 'from_address': 'sender@example.test'}}
    }
    contact = Contact(workspace_id=workspace_id, name='Recipient', email='recipient@example.test')
    db.session.add(contact)
    db.session.flush()
    enqueue(workspace_id, contact, 'email', 'Hello', 'Test', str(uuid4()), user_id)
    db.session.commit()
    entered = Event()
    release = Event()
    calls = []

    def deliver(thread, message):
        calls.append(message.id)
        entered.set()
        assert release.wait(timeout=10)
        return 'provider-id'

    monkeypatch.setattr('app.services.communications.deliver', deliver)

    def work():
        with app.app_context():
            return dispatch(workspace_id, limit=1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(work)
        try:
            assert entered.wait(timeout=10)
            assert pool.submit(work).result(timeout=10) == []
        finally:
            release.set()
        assert len(first.result(timeout=10)) == 1
    assert len(calls) == 1
    db.session.expire_all()
    assert InboxMessage.query.filter_by(workspace_id=workspace_id).one().status == 'sent'
