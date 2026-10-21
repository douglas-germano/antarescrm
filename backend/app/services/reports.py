"""Period report: one pass over the account's data, with the previous equal period for comparison."""

from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from ..access import account_users
from ..extensions import db
from ..models import (
    Activity,
    AutomationRun,
    Contact,
    Opportunity,
    PipelineStage,
    StageHistory,
    Task,
    WhatsAppMessage,
    Workspace,
)

SALES_STALE_DAYS = 14


def money(value):
    return float(Decimal(value or 0))


def bounds(day_start, day_end, tz):
    return (
        datetime.combine(day_start, time.min, tzinfo=tz),
        datetime.combine(day_end + timedelta(days=1), time.min, tzinfo=tz),
    )


def in_range(value, lower, upper):
    return value is not None and lower <= value < upper


def bucket_key(day, granularity):
    if granularity == 'month':
        return day.replace(day=1)
    if granularity == 'week':
        return day - timedelta(days=day.weekday())
    return day


def build(workspace_id, start, end, pipeline_id=None, today=None):

    ws = db.session.get(Workspace, workspace_id)
    tz = ZoneInfo(ws.timezone)
    days = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    lower, upper = bounds(start, end, tz)
    p_lower, p_upper = bounds(prev_start, prev_end, tz)
    granularity = 'day' if days <= 31 else ('week' if days <= 120 else 'month')
    today = today or datetime.now(tz).date()

    stages = PipelineStage.query.filter_by(workspace_id=workspace_id).order_by(PipelineStage.position).all()
    stage_by_id = {s.id: s for s in stages}

    def pipeline_of(stage_id):
        return stage_by_id[stage_id].pipeline_id if stage_id in stage_by_id else None

    def wanted(opp):
        if not pipeline_id or pipeline_id == 'all':
            return True
        return (
            (pipeline_of(opp.stage_id) is None)
            if pipeline_id == 'default'
            else (pipeline_of(opp.stage_id) == pipeline_id)
        )

    deals = [o for o in Opportunity.query.filter_by(workspace_id=workspace_id).all() if wanted(o)]
    contacts = Contact.query.filter_by(workspace_id=workspace_id, archived=False).all()
    contact_by_id = {c.id: c for c in contacts}

    users = {u.id: u.name for u in account_users(workspace_id)}

    def period_stats(lo, up):
        won = [o for o in deals if o.status == 'won' and in_range(o.closed_at, lo, up)]
        lost = [o for o in deals if o.status == 'lost' and in_range(o.closed_at, lo, up)]
        created = [o for o in deals if in_range(o.created_at, lo, up)]
        new_contacts = [c for c in contacts if in_range(c.created_at, lo, up)]
        closed = len(won) + len(lost)
        cycle = [(o.closed_at - o.created_at).total_seconds() / 86400 for o in won if o.closed_at and o.created_at]
        return (
            {
                'won_amount': sum(money(o.amount) for o in won),
                'won_count': len(won),
                'lost_count': len(lost),
                'lost_amount': sum(money(o.amount) for o in lost),
                'conversion_rate': round(100 * len(won) / closed, 1) if closed else 0,
                'average_ticket': (sum(money(o.amount) for o in won) / len(won)) if won else 0,
                'new_deals': len(created),
                'new_deals_amount': sum(money(o.amount) for o in created),
                'new_contacts': len(new_contacts),
                'sales_cycle_days': round(sum(cycle) / len(cycle), 1) if cycle else None,
            },
            won,
            lost,
            created,
            new_contacts,
        )

    current, won, lost, created, new_contacts = period_stats(lower, upper)
    previous, *_ = period_stats(p_lower, p_upper)

    # Open pipeline right now (not period-bound).
    open_deals = [o for o in deals if o.status == 'open']
    probability = {s.id: (s.probability or 0) for s in stages}
    moved_at = {}
    for row in StageHistory.query.filter_by(workspace_id=workspace_id).all():
        moved_at[row.opportunity_id] = max(moved_at.get(row.opportunity_id, row.created_at), row.created_at)
    last_touch = {}
    for row in Activity.query.filter_by(workspace_id=workspace_id, status='completed').all():
        if row.opportunity_id:
            last_touch[row.opportunity_id] = max(last_touch.get(row.opportunity_id, row.scheduled_at), row.scheduled_at)
    now_dt = datetime.now(tz)

    def idle_days(o):
        latest = max([t for t in (moved_at.get(o.id), last_touch.get(o.id), o.created_at) if t])
        return max(0, (now_dt - latest).days)

    pipeline = {
        'open_count': len(open_deals),
        'open_amount': sum(money(o.amount) for o in open_deals),
        'weighted_amount': sum(money(o.amount) * probability.get(o.stage_id, 0) / 100 for o in open_deals),
        'overdue_close': sum(1 for o in open_deals if o.expected_close_date and o.expected_close_date < today),
        'stale_count': sum(1 for o in open_deals if idle_days(o) >= SALES_STALE_DAYS),
        'stale_amount': sum(money(o.amount) for o in open_deals if idle_days(o) >= SALES_STALE_DAYS),
        'closing_30d_amount': sum(
            money(o.amount)
            for o in open_deals
            if o.expected_close_date and today <= o.expected_close_date <= today + timedelta(days=30)
        ),
    }
    top_open = sorted(open_deals, key=lambda o: -money(o.amount))[:5]
    top_stale = sorted((o for o in open_deals if idle_days(o) >= SALES_STALE_DAYS), key=lambda o: -idle_days(o))[:5]

    def deal_row(o):
        return {
            'id': o.id,
            'title': o.title,
            'amount': money(o.amount),
            'contact': (contact_by_id.get(o.contact_id).name if contact_by_id.get(o.contact_id) else None),
            'stage': stage_by_id[o.stage_id].name if o.stage_id in stage_by_id else '',
            'owner': users.get(o.owner_id),
            'idle_days': idle_days(o),
            'expected_close_date': o.expected_close_date.isoformat() if o.expected_close_date else None,
        }

    # Time series.
    series = defaultdict(lambda: {'new_contacts': 0, 'new_deals': 0, 'won_amount': 0.0, 'won_count': 0})
    cursor = start
    while cursor <= end:
        series[bucket_key(cursor, granularity)]
        cursor += timedelta(days=1)
    for c in new_contacts:
        series[bucket_key(c.created_at.astimezone(tz).date(), granularity)]['new_contacts'] += 1
    for o in created:
        series[bucket_key(o.created_at.astimezone(tz).date(), granularity)]['new_deals'] += 1
    for o in won:
        point = series[bucket_key(o.closed_at.astimezone(tz).date(), granularity)]
        point['won_amount'] += money(o.amount)
        point['won_count'] += 1
    timeline = [{'date': k.isoformat(), **v} for k, v in sorted(series.items())]

    # Funnel of the chosen pipeline: how many deals entered each stage in the period and where they are now.
    funnel_pipeline = None if pipeline_id in (None, 'all', 'default') else pipeline_id
    funnel_stages = [s for s in stages if s.pipeline_id == funnel_pipeline]
    entered = defaultdict(set)
    for row in StageHistory.query.filter_by(workspace_id=workspace_id).all():
        if in_range(row.created_at, lower, upper):
            entered[row.to_stage_id].add(row.opportunity_id)
    funnel, previous_entered = [], None
    for s in funnel_stages:
        here = [o for o in open_deals if o.stage_id == s.id]
        count = len(entered[s.id])
        funnel.append(
            {
                'stage_id': s.id,
                'name': s.name,
                'color': s.color,
                'entered': count,
                'open_count': len(here),
                'open_amount': sum(money(o.amount) for o in here),
                'probability': s.probability,
                'step_rate': (round(100 * count / previous_entered, 1) if previous_entered else None),
            }
        )
        previous_entered = count or previous_entered

    # Team.
    team = {}

    def member(owner_id):
        return team.setdefault(
            owner_id,
            {
                'owner_id': owner_id,
                'name': users.get(owner_id, 'Sem responsável'),
                'won_count': 0,
                'won_amount': 0.0,
                'lost_count': 0,
                'open_count': 0,
                'open_amount': 0.0,
                'activities_done': 0,
                'tasks_done': 0,
            },
        )

    for o in won:
        m = member(o.owner_id)
        m['won_count'] += 1
        m['won_amount'] += money(o.amount)
    for o in lost:
        member(o.owner_id)['lost_count'] += 1
    for o in open_deals:
        m = member(o.owner_id)
        m['open_count'] += 1
        m['open_amount'] += money(o.amount)
    activities = Activity.query.filter_by(workspace_id=workspace_id).all()
    tasks = Task.query.filter_by(workspace_id=workspace_id).all()
    for a in activities:
        if a.status == 'completed' and in_range(a.scheduled_at, lower, upper):
            member(a.owner_id)['activities_done'] += 1
    for t in tasks:
        if t.status == 'done' and in_range(t.completed_at, lower, upper):
            member(t.assignee_id)['tasks_done'] += 1
    for m in team.values():
        closed = m['won_count'] + m['lost_count']
        m['conversion_rate'] = round(100 * m['won_count'] / closed, 1) if closed else 0
    team_rows = sorted(team.values(), key=lambda m: (-m['won_amount'], -m['open_amount']))

    # Sources: new contacts and revenue by contact origin.
    sources = defaultdict(lambda: {'contacts': 0, 'deals': 0, 'won_count': 0, 'won_amount': 0.0})
    for c in new_contacts:
        sources[c.source or 'Sem origem']['contacts'] += 1
    for o in created:
        sources[(contact_by_id.get(o.contact_id).source if contact_by_id.get(o.contact_id) else None) or 'Sem origem'][
            'deals'
        ] += 1
    for o in won:
        s = sources[
            (contact_by_id.get(o.contact_id).source if contact_by_id.get(o.contact_id) else None) or 'Sem origem'
        ]
        s['won_count'] += 1
        s['won_amount'] += money(o.amount)
    source_rows = sorted(
        ({'source': k, **v} for k, v in sources.items()), key=lambda r: (-r['won_amount'], -r['contacts'])
    )[:8]

    reasons = defaultdict(lambda: {'count': 0, 'amount': 0.0})
    for o in lost:
        r = reasons[(o.loss_reason or 'Não informado').strip() or 'Não informado']
        r['count'] += 1
        r['amount'] += money(o.amount)
    loss_rows = sorted(({'reason': k, **v} for k, v in reasons.items()), key=lambda r: -r['count'])[:8]

    # Day-to-day operation.
    kind_rows = defaultdict(lambda: {'completed': 0, 'pending': 0, 'cancelled': 0})
    for a in activities:
        if in_range(a.scheduled_at, lower, upper):
            kind_rows[a.kind][a.status if a.status in ('completed', 'pending', 'cancelled') else 'pending'] += 1
    task_stats = {
        'created': sum(1 for t in tasks if in_range(t.created_at, lower, upper)),
        'done': sum(1 for t in tasks if t.status == 'done' and in_range(t.completed_at, lower, upper)),
        'open': sum(1 for t in tasks if t.status in ('todo', 'doing')),
        'overdue': sum(1 for t in tasks if t.status in ('todo', 'doing') and t.due_date and t.due_date < today),
    }
    messages = WhatsAppMessage.query.filter(WhatsAppMessage.workspace_id == workspace_id).all()
    message_stats = {
        'received': sum(1 for m in messages if m.direction == 'in' and in_range(m.occurred_at, lower, upper)),
        'sent': sum(1 for m in messages if m.direction == 'out' and in_range(m.occurred_at, lower, upper)),
    }
    runs = AutomationRun.query.filter_by(workspace_id=workspace_id).all()
    automation_stats = {
        'runs': sum(1 for r in runs if in_range(r.created_at, lower, upper)),
        'failed': sum(1 for r in runs if r.status == 'failed' and in_range(r.created_at, lower, upper)),
    }

    return {
        'period': {
            'start': start.isoformat(),
            'end': end.isoformat(),
            'days': days,
            'previous_start': prev_start.isoformat(),
            'previous_end': prev_end.isoformat(),
            'granularity': granularity,
        },
        'current': current,
        'previous': previous,
        'pipeline': pipeline,
        'timeline': timeline,
        'funnel': funnel,
        'team': team_rows,
        'sources': source_rows,
        'loss_reasons': loss_rows,
        'activities': [{'kind': k, **v} for k, v in sorted(kind_rows.items())],
        'tasks': task_stats,
        'messages': message_stats,
        'automations': automation_stats,
        'top_open': [deal_row(o) for o in top_open],
        'top_stale': [deal_row(o) for o in top_stale],
    }
