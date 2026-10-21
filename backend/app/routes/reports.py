from datetime import timedelta, datetime, time
from zoneinfo import ZoneInfo
from flask import Blueprint, g, request
from sqlalchemy import func
from ..extensions import db
from ..models import Task, Contact, Company, Opportunity, Activity, PipelineStage, User, Workspace, Booking
from ..common import require, get, APIError, query, date_arg, dates_valid, today, money_string

bp = Blueprint('reports', __name__)

OPEN_TASK = Task.status.in_(['todo', 'doing'])


def sales_summary():
    rows = query(Opportunity).all()
    won = [r for r in rows if r.status == 'won']
    lost = [r for r in rows if r.status == 'lost']
    opened = [r for r in rows if r.status == 'open']
    total = lambda items: money_string(sum((r.amount for r in items), 0))
    return {'open_count': len(opened), 'won_count': len(won), 'lost_count': len(lost),
            'open_amount': total(opened), 'won_amount': total(won), 'lost_amount': total(lost),
            'conversion_rate': round(100 * len(won) / (len(won) + len(lost)), 1) if won or lost else 0,
            'average_ticket': money_string(sum((r.amount for r in won), 0) / len(won)) if won else '0.00'}


@bp.get('/dashboard')
@require()
def dashboard():
    return {
        'contacts': query(Contact).filter_by(archived=False).count(),
        'companies': query(Company).filter_by(archived=False).count(),
        'open_tasks': query(Task).filter(OPEN_TASK).count(),
        'overdue_tasks': query(Task).filter(OPEN_TASK, Task.due_date < today()).count(),
        'my_tasks': query(Task).filter(OPEN_TASK, Task.assignee_id == g.user.id).count(),
        'sales': sales_summary(),
    }


@bp.get('/reports/funnel')
@require()
def funnel():
    stages = query(PipelineStage).order_by(PipelineStage.position).all()
    rows = (query(Opportunity).filter_by(status='open')
            .with_entities(Opportunity.stage_id, func.count(Opportunity.id), func.coalesce(func.sum(Opportunity.amount), 0))
            .group_by(Opportunity.stage_id).all())
    data = {r[0]: (r[1], r[2]) for r in rows}
    return {'items': [{'stage_id': s.id, 'name': s.name, 'color': s.color, 'count': data.get(s.id, (0, 0))[0],
                       'amount': money_string(data.get(s.id, (0, 0))[1])} for s in stages]}


@bp.get('/reports/sales-by-owner')
@require()
def sales_by_owner():
    rows = (query(Opportunity).filter(Opportunity.status.in_(['won', 'lost']))
            .with_entities(Opportunity.owner_id, Opportunity.status, func.count(Opportunity.id), func.coalesce(func.sum(Opportunity.amount), 0))
            .group_by(Opportunity.owner_id, Opportunity.status).all())
    from ..access import account_users
    names = {u.id: u.name for u in account_users(g.workspace_id)}
    result = {}
    for owner, status, count, amount in rows:
        item = result.setdefault(owner, {'owner_id': owner, 'name': names.get(owner, 'Sem responsável'),
                                         'won_count': 0, 'lost_count': 0, 'won_amount': '0.00'})
        item[f'{status}_count'] = count
        if status == 'won':
            item['won_amount'] = money_string(amount)
    return {'items': sorted(result.values(), key=lambda x: float(x['won_amount']), reverse=True)}


@bp.get('/reports/won-by-month')
@require()
def won_by_month():
    workspace = db.session.get(Workspace, g.workspace_id)
    day = today().replace(day=1)
    month = (func.strftime('%Y-%m', Opportunity.closed_at) if db.session.get_bind().dialect.name == 'sqlite'
             else func.date_trunc('month', func.timezone(workspace.timezone, Opportunity.closed_at)))
    month_index = day.year * 12 + day.month - 1 - 11
    since = datetime(month_index // 12, month_index % 12 + 1, 1, tzinfo=ZoneInfo(workspace.timezone))
    rows = (query(Opportunity).filter(Opportunity.status == 'won', Opportunity.closed_at >= since)
            .with_entities(month, func.count(Opportunity.id), func.coalesce(func.sum(Opportunity.amount), 0))
            .group_by(month).order_by(month).all())
    return {'items': [{'month': (r[0][:7] if isinstance(r[0], str) else r[0].strftime('%Y-%m')), 'count': r[1], 'amount': money_string(r[2])} for r in rows]}


@bp.get('/reports/loss-reasons')
@require()
def loss_reasons():
    rows = (query(Opportunity).filter_by(status='lost')
            .with_entities(Opportunity.loss_reason, func.count(Opportunity.id))
            .group_by(Opportunity.loss_reason).order_by(func.count(Opportunity.id).desc()).limit(10).all())
    return {'items': [{'reason': r[0] or 'Não informado', 'count': r[1]} for r in rows]}


@bp.get('/reports/activities')
@require()
def activity_report():
    start = date_arg('start', today() - timedelta(days=30))
    end = date_arg('end', today())
    dates_valid(start, end)
    tz = ZoneInfo(db.session.get(Workspace, g.workspace_id).timezone)
    lower = datetime.combine(start, time.min, tzinfo=tz)
    upper = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz)
    rows = (query(Activity).filter(Activity.scheduled_at >= lower, Activity.scheduled_at < upper)
            .with_entities(Activity.kind, Activity.status, func.count(Activity.id)).group_by(Activity.kind, Activity.status).all())
    return {'items': [{'kind': r[0], 'status': r[1], 'count': r[2]} for r in rows]}


@bp.get('/calendar')
@require()
def calendar():
    start = date_arg('start', today())
    end = date_arg('end', start + timedelta(days=30))
    dates_valid(start, end)
    tz = ZoneInfo(db.session.get(Workspace, g.workspace_id).timezone)
    lower = datetime.combine(start, time.min, tzinfo=tz)
    upper = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz)
    events = []
    for row in query(Task).filter(Task.due_date.between(start, end), OPEN_TASK).all():
        events.append({'kind': 'task', 'id': row.id, 'title': row.title, 'date': row.due_date.isoformat(),
                       'contact_id': row.contact_id, 'opportunity_id': row.opportunity_id})
    activities = query(Activity).filter(Activity.scheduled_at >= lower, Activity.scheduled_at < upper, Activity.status == 'pending').all()
    reservations = {row.activity_id: row for row in query(Booking).filter(Booking.activity_id.in_([row.id for row in activities])).all()}
    contacts = {row.id: row.name for row in query(Contact).filter(Contact.id.in_([row.contact_id for row in activities if row.contact_id])).all()}
    for row in activities:
        reservation = reservations.get(row.id)
        events.append({'kind': row.kind, 'id': row.id, 'title': row.title, 'date': row.scheduled_at.isoformat(),
                       'contact_id': row.contact_id, 'contact_name': contacts.get(row.contact_id),
                       'opportunity_id': row.opportunity_id, 'notes': row.notes,
                       'booking_id': reservation.id if reservation else None,
                       'ends_at': reservation.ends_at.isoformat() if reservation else None})
    return {'items': sorted(events, key=lambda e: e['date'])}


@bp.get('/reports/follow-ups')
@require()
def followups():
    from flask import request
    from ..services.followups import followup_report
    return followup_report(mine=request.args.get('mine') == 'true')


@bp.get('/reports/overview')
@require()
def overview():
    from ..services.reports import build
    end = date_arg('end', today())
    start = date_arg('start', end - timedelta(days=29))
    dates_valid(start, end)
    if (end - start).days > 800:
        raise APIError('Escolha um período de até 800 dias.', 422)
    pipeline_id = request.args.get('pipeline_id')
    if pipeline_id and pipeline_id not in ('all', 'default'):
        from ..models import Pipeline
        get(Pipeline, pipeline_id)
    return build(g.workspace_id, start, end, pipeline_id, today())
