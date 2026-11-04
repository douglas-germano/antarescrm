from uuid import uuid4

from app.extensions import db
from app.models import AutomationRule


def submit_body(**kw):
    return dict(
        submission_key=str(uuid4()),
        name='Lead de teste',
        email='lead@example.com',
        phone='65999999999',
        consent=True,
        **kw,
    )


def rule(d, **kw):
    row = AutomationRule(
        workspace_id=kw.pop('workspace_id', d['ws'].id),
        name='Primeiro atendimento',
        event=kw.pop('event', 'form.submitted'),
        task_title='Retornar ao lead',
        active=kw.pop('active', True),
        due_days=kw.pop('due_days', 0),
        **kw,
    )
    db.session.add(row)
    db.session.commit()
    return row
