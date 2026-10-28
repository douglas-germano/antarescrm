"""Account-scoped server filtering, pagination inputs and list summaries."""

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from flask import g
from sqlalchemy import case, func

from ..access import account_users
from ..common import APIError, get, money_string, query, today
from ..extensions import db
from ..models import Activity, Company, Contact, Opportunity, Pipeline, PipelineStage, StageHistory, Task, User, now
from .text_search import search_columns


def task_query(args):
    q = query(Task).outerjoin(Contact, db.and_(Contact.id == Task.contact_id, Contact.workspace_id == g.workspace_id))
    for field in ('status', 'assignee_id', 'contact_id', 'company_id', 'opportunity_id', 'priority'):
        if args.get(field):
            q = q.filter(getattr(Task, field) == args[field])
    if args.get('view') in ('open', 'closed'):
        q = q.filter(Task.status.in_(('todo', 'doing') if args['view'] == 'open' else ('done', 'cancelled')))
    if args.get('mine') == 'true':
        q = q.filter(Task.assignee_id == g.user.id)
    term = (args.get('search') or '').strip()
    if term:
        q = search_columns(q, term, (Task.title, Contact.name, Contact.phone), Contact.phone)
    return q.order_by(Task.due_date.asc().nullslast(), Task.created_at.desc(), Task.id)


def contact_query(args):
    q = query(Contact).filter_by(archived=args.get('archived') == 'true')
    for field in ('company_id', 'owner_id'):
        if args.get(field):
            column = getattr(Contact, field)
            q = q.filter(column.is_(None) if args[field] == 'unassigned' else column == args[field])
    if args.get('source'):
        q = q.filter(Contact.source == args['source'])
    if args.get('has_email') in ('true', 'false'):
        has_email = func.length(func.trim(func.coalesce(Contact.email, ''))) > 0
        q = q.filter(has_email if args['has_email'] == 'true' else ~has_email)
    if args.get('tag'):
        q = q.filter(tag_predicate(args['tag']))
    q = q.outerjoin(Company, db.and_(Company.id == Contact.company_id, Company.workspace_id == g.workspace_id))
    q = search_columns(
        q,
        (args.get('search') or '').strip(),
        (
            Contact.name,
            Contact.phone,
            Contact.email,
            Company.name,
            db.cast(Contact.tags, db.String),
            db.cast(Contact.custom_fields, db.String),
        ),
        Contact.phone,
    )
    return q.order_by(Contact.name, Contact.id)


def tag_predicate(tag):
    if db.session.get_bind().dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import JSONB

        return db.cast(Contact.tags, JSONB).contains([tag])
    entries = func.json_each(Contact.tags).table_valued('value').alias('contact_tag')
    return db.select(1).select_from(entries).where(entries.c.value == tag).correlate(Contact).exists()


def contact_tags():
    return sorted(
        {
            tag
            for (tags,) in query(Contact).filter_by(archived=False).with_entities(Contact.tags)
            for tag in (tags or [])
        }
    )


def enrich_people(items):
    ids = {item.get('contact_id') for item in items} - {None}
    contacts = {row.id: row for row in query(Contact).filter(Contact.id.in_(ids))} if ids else {}
    company_ids = {item.get('company_id') for item in items} - {None}
    companies = {row.id: row.name for row in query(Company).filter(Company.id.in_(company_ids))} if company_ids else {}
    users = {row.id: row.name for row in account_users(g.workspace_id)}
    for item in items:
        contact = contacts.get(item.get('contact_id'))
        item.update(
            contact_name=contact.name if contact else None,
            contact_phone=contact.phone if contact else None,
            contact_email=contact.email if contact else None,
            company_name=companies.get(item.get('company_id')),
            owner_name=users.get(item.get('owner_id')),
            assignee_name=users.get(item.get('assignee_id')),
        )


def opportunity_query(args):
    q = query(Opportunity).join(PipelineStage, PipelineStage.id == Opportunity.stage_id)
    q = q.outerjoin(Contact, db.and_(Contact.id == Opportunity.contact_id, Contact.workspace_id == g.workspace_id))
    q = q.outerjoin(Company, db.and_(Company.id == Opportunity.company_id, Company.workspace_id == g.workspace_id))
    identifier = args.get('pipeline_id')
    if identifier:
        if identifier != 'default':
            get(Pipeline, identifier)
        q = q.filter(
            PipelineStage.pipeline_id.is_(None) if identifier == 'default' else PipelineStage.pipeline_id == identifier
        )
    for field in ('status', 'stage_id', 'contact_id', 'company_id', 'owner_id'):
        if args.get(field):
            column = getattr(Opportunity, field)
            q = q.filter(column.is_(None) if args[field] == 'none' else column == args[field])
    if args.get('source'):
        q = q.filter(Contact.source == args['source'])
    term = (args.get('search') or '').strip()
    if term:
        q = search_columns(
            q, term, (Opportunity.title, Contact.name, Contact.phone, Contact.email, Company.name), Contact.phone
        )
    for parameter, lower in (('min_amount', True), ('max_amount', False)):
        if args.get(parameter):
            try:
                value = Decimal(args[parameter])
                if not value.is_finite() or value < 0:
                    raise ValueError
            except (InvalidOperation, ValueError):
                raise APIError('Valor de filtro inválido.', 422) from None
            q = q.filter(Opportunity.amount >= value if lower else Opportunity.amount <= value)
    day = today()
    due = Opportunity.expected_close_date
    period = args.get('period')
    if period == 'overdue':
        q = q.filter(due < day)
    elif period == 'week':
        q = q.filter(due >= day, due <= day + timedelta(days=7))
    elif period == 'month':
        first = day.replace(day=1)
        next_month = (first + timedelta(days=32)).replace(day=1)
        q = q.filter(due >= first, due < next_month)
    elif period == 'none':
        q = q.filter(due.is_(None))
    if args.get('attention') == 'true' and args.get('status') == 'open':
        activity = query(Activity).filter(Activity.opportunity_id == Opportunity.id, Activity.status == 'pending')
        task = query(Task).filter(
            Task.opportunity_id == Opportunity.id, Task.status.in_(('todo', 'doing')), Task.due_date.isnot(None)
        )
        q = q.filter(
            db.or_(
                activity.filter(Activity.scheduled_at < now()).exists(),
                task.filter(Task.due_date < day).exists(),
                due < day,
                db.and_(~activity.exists(), ~task.exists()),
            )
        )
    return q


def opportunity_order(q, args):
    key = args.get('sort', 'updated')
    columns = {
        'title': func.lower(Opportunity.title),
        'stage': PipelineStage.position,
        'amount': Opportunity.amount,
        'close': Opportunity.expected_close_date,
        'owner': db.select(func.lower(User.name)).where(User.id == Opportunity.owner_id).scalar_subquery(),
        'updated': Opportunity.updated_at,
    }
    if key == 'stale':
        moved = (
            query(StageHistory)
            .filter(StageHistory.opportunity_id == Opportunity.id)
            .with_entities(func.max(StageHistory.created_at))
            .scalar_subquery()
        )
        touched = (
            query(Activity)
            .filter(Activity.opportunity_id == Opportunity.id, Activity.status == 'completed')
            .with_entities(func.max(Activity.scheduled_at))
            .scalar_subquery()
        )
        stage_at = func.coalesce(moved, Opportunity.created_at)
        column = case((touched > stage_at, touched), else_=stage_at)
        # More days stale means an older timestamp.
        descending = args.get('direction') != 'desc'
    else:
        column = columns.get(key, Opportunity.updated_at)
        descending = args.get('direction', 'desc') == 'desc'
    return q.order_by((column.desc() if descending else column.asc()).nullslast(), Opportunity.id)


def opportunity_summary(q):
    rows = (
        q.with_entities(
            Opportunity.stage_id, func.count(Opportunity.id), func.sum(Opportunity.amount), PipelineStage.probability
        )
        .group_by(Opportunity.stage_id, PipelineStage.probability)
        .all()
    )
    stages = {stage: {'count': count, 'amount': money_string(amount)} for stage, count, amount, _ in rows}
    return {
        'stages': stages,
        'amount': money_string(sum((amount for _, _, amount, _ in rows), Decimal(0))),
        'weighted': money_string(
            sum((amount * Decimal(probability or 0) / 100 for _, _, amount, probability in rows), Decimal(0))
        ),
    }


def contact_sources():
    return [
        value
        for (value,) in query(Contact)
        .filter(Contact.source.isnot(None), Contact.source != '')
        .with_entities(Contact.source)
        .distinct()
        .order_by(Contact.source)
    ]
