"""Version history of automation rules: every saved change is kept and any version can be restored."""

from ..extensions import db
from ..models import AutomationRuleVersion, User

FIELDS = (
    'name',
    'event',
    'source',
    'task_title',
    'due_days',
    'assignee_id',
    'conditions',
    'required_tag',
    'actions',
    'stop_on_reply',
)
LABELS = {
    'name': 'nome',
    'event': 'gatilho',
    'source': 'origem',
    'task_title': 'título da tarefa',
    'due_days': 'prazo',
    'assignee_id': 'responsável',
    'conditions': 'condições',
    'required_tag': 'tag exigida',
    'actions': 'passos',
    'stop_on_reply': 'interromper ao responder',
}


def snapshot(rule):
    return {field: getattr(rule, field) for field in FIELDS}


def latest(rule):
    return (
        AutomationRuleVersion.query.filter_by(workspace_id=rule.workspace_id, rule_id=rule.id)
        .order_by(AutomationRuleVersion.number.desc())
        .first()
    )


def record(rule, author_id=None, note=None):
    """Save the rule's current configuration unless it equals the last version (e.g. only paused or resumed)."""
    db.session.flush()
    last = latest(rule)
    current = snapshot(rule)
    if last and last.snapshot == current:
        return None
    version = AutomationRuleVersion(
        workspace_id=rule.workspace_id,
        rule_id=rule.id,
        number=(last.number + 1) if last else 1,
        snapshot=current,
        author_id=author_id,
        note=note,
    )
    db.session.add(version)
    db.session.flush()
    return version


def ensure_baseline(rule):
    """Rules saved before the history existed get their current configuration as version 1."""
    if not latest(rule):
        record(rule, None, 'Versão anterior ao histórico')


def changes(previous, current):
    if previous is None:
        return []
    return [LABELS[field] for field in FIELDS if previous.get(field) != current.get(field)]


def history(rule):
    rows = (
        AutomationRuleVersion.query.filter_by(workspace_id=rule.workspace_id, rule_id=rule.id)
        .order_by(AutomationRuleVersion.number)
        .all()
    )
    authors = (
        {
            user.id: user.name
            for user in User.query.filter(User.id.in_({row.author_id for row in rows if row.author_id})).all()
        }
        if rows
        else {}
    )
    items, previous = [], None
    for row in rows:
        item = row.to_dict()
        item['author_name'] = authors.get(row.author_id)
        item['changes'] = changes(previous, row.snapshot)
        item['current'] = False
        items.append(item)
        previous = row.snapshot
    if items:
        items[-1]['current'] = items[-1]['snapshot'] == snapshot(rule)
    return list(reversed(items))
