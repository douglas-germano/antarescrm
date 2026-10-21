"""Scheduled next steps for open deals, using existing activities and tasks."""
from collections import defaultdict
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
from flask import g
from ..common import query, money_string
from ..extensions import db
from ..models import Activity, Task, Opportunity, Contact, Company, User, Workspace, now


def followup_report(mine=False):
    workspace = db.session.get(Workspace, g.workspace_id)
    tz = ZoneInfo(workspace.timezone)
    current = now()
    current_day = current.astimezone(tz).date()
    deals_query = query(Opportunity).filter_by(status='open')
    if mine:
        deals_query = deals_query.filter_by(owner_id=g.user.id)
    deals = deals_query.all()
    ids = [deal.id for deal in deals]
    actions = defaultdict(list)
    if ids:
        for activity in query(Activity).filter(Activity.opportunity_id.in_(ids), Activity.status == 'pending').all():
            due = activity.scheduled_at
            due = due.replace(tzinfo=timezone.utc) if due.tzinfo is None else due
            actions[activity.opportunity_id].append((due, {
                'id': activity.id, 'type': 'activity', 'title': activity.title,
                'scheduled_at': due.isoformat(), 'overdue': due < current,
            }))
        for task in query(Task).filter(Task.opportunity_id.in_(ids), Task.status.in_(['todo', 'doing']), Task.due_date.isnot(None)).all():
            # Date-only tasks remain on time throughout their local due date.
            due = datetime.combine(task.due_date, time.max, tzinfo=tz)
            actions[task.opportunity_id].append((due, {
                'id': task.id, 'type': 'task', 'title': task.title,
                'scheduled_at': task.due_date.isoformat(), 'overdue': task.due_date < current_day,
            }))
    contacts = {r.id: r.name for r in query(Contact).all()} if ids else {}
    companies = {r.id: r.name for r in query(Company).all()} if ids else {}
    from ..access import account_users
    owners = {r.id: r.name for r in account_users(g.workspace_id)} if ids else {}
    items = []
    counts = {'overdue_action': 0, 'overdue_close': 0, 'no_next_action': 0}
    order = {'overdue_action': 0, 'overdue_close': 1, 'no_next_action': 2}
    for deal in deals:
        scheduled = sorted(actions[deal.id], key=lambda entry: (entry[0], entry[1]['id']))
        next_action = scheduled[0][1] if scheduled else None
        if next_action and next_action['overdue']:
            reason = 'overdue_action'
        elif deal.expected_close_date and deal.expected_close_date < current_day:
            reason = 'overdue_close'
        elif not next_action:
            reason = 'no_next_action'
        else:
            continue
        counts[reason] += 1
        items.append({
            'id': deal.id, 'title': deal.title, 'amount': money_string(deal.amount),
            'contact_id': deal.contact_id, 'contact_name': contacts.get(deal.contact_id),
            'company_id': deal.company_id, 'company_name': companies.get(deal.company_id),
            'owner_id': deal.owner_id, 'owner_name': owners.get(deal.owner_id),
            'stage_id': deal.stage_id, 'expected_close_date': deal.expected_close_date.isoformat() if deal.expected_close_date else None,
            'reason': reason, 'next_action': next_action,
        })
    items.sort(key=lambda row: (order[row['reason']], (row['next_action'] or {}).get('scheduled_at') or row['expected_close_date'] or '', row['title']))
    return {'items': items, 'total': len(items), 'summary': counts, 'timezone': workspace.timezone, 'generated_at': current.isoformat()}
