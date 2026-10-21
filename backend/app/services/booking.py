"""Availability and transactional bookings; no provider I/O during reservations."""
from datetime import datetime, time, timedelta, timezone, date
from zoneinfo import ZoneInfo
import hashlib
from sqlalchemy import func
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask import current_app
from ..extensions import db
from ..models import BookingCalendar, Booking, Workspace, Activity, Contact, now, AuditLog
from ..common import APIError
from ..access import account_users

CONSENT = 'Autorizo o contato para tratar deste agendamento.'


def lock(key):
    if db.session.get_bind().dialect.name == 'postgresql':
        value = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], 'big', signed=True)
        db.session.execute(db.text('SELECT pg_advisory_xact_lock(:key)'), {'key': value})


def published(calendar_id):
    calendar = BookingCalendar.query.join(Workspace, Workspace.id == BookingCalendar.workspace_id).filter(
        BookingCalendar.id == str(calendar_id), BookingCalendar.active.is_(True), Workspace.active.is_(True)).first()
    if not calendar or (calendar.assignee_id and calendar.assignee_id not in {u.id for u in account_users(calendar.workspace_id) if u.active}):
        raise APIError('Agenda indisponível.', 404)
    return calendar


def timezone_for(calendar):
    return ZoneInfo(db.session.get(Workspace, calendar.workspace_id).timezone)


def public_copy(calendar):
    return {'name': calendar.name, 'description': calendar.description, 'duration_minutes': calendar.duration_minutes,
            'timezone': str(timezone_for(calendar)), 'consent_text': CONSENT,
            'horizon_days': calendar.horizon_days}


def availability(calendar, day):
    tz, current = timezone_for(calendar), now()
    today = current.astimezone(tz).date()
    if day < today or day > today + timedelta(days=calendar.horizon_days): return []
    entries = calendar.availability.get(str(day.weekday()), [])
    result = []
    duration = timedelta(minutes=calendar.duration_minutes)
    buffer = timedelta(minutes=calendar.buffer_minutes)
    # Every calendar of the same assignee shares the occupied interval.
    reservations = Booking.query.filter_by(workspace_id=calendar.workspace_id, assignee_id=calendar.assignee_id, status='confirmed').filter(
        Booking.starts_at < datetime.combine(day + timedelta(days=2), time.min, tzinfo=tz),
        Booking.ends_at > datetime.combine(day - timedelta(days=1), time.min, tzinfo=tz)).all()
    meetings = Activity.query.filter_by(workspace_id=calendar.workspace_id, owner_id=calendar.assignee_id, status='pending').filter(
        Activity.kind.in_(['meeting', 'call']),
        Activity.scheduled_at < datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz),
        Activity.scheduled_at > datetime.combine(day, time.min, tzinfo=tz) - duration - buffer,
        ~Activity.id.in_([b.activity_id for b in reservations])).all()
    for entry in entries:
        cursor = datetime.combine(day, time.fromisoformat(entry['start']), tzinfo=tz)
        upper = datetime.combine(day, time.fromisoformat(entry['end']), tzinfo=tz)
        while cursor + duration <= upper:
            start = cursor.astimezone(timezone.utc)
            end = (cursor + duration).astimezone(timezone.utc)
            # Nonexistent/ambiguous local times must not produce misleading slots.
            real = start.astimezone(tz).replace(tzinfo=None) == cursor.replace(tzinfo=None)
            unambiguous = cursor.replace(fold=0).utcoffset() == cursor.replace(fold=1).utcoffset()
            if real and unambiguous and end > start and start >= current + timedelta(minutes=calendar.lead_minutes):
                busy = any(start < b.ends_at + timedelta(minutes=b.buffer_minutes) and end + buffer > b.starts_at for b in reservations)
                if not busy:
                    # Block manually scheduled meetings too; booking activities are already represented above.
                    busy_meeting = any(start < a.scheduled_at + duration + buffer and end + buffer > a.scheduled_at for a in meetings)
                    if not busy_meeting: result.append(start.isoformat())
            cursor += duration + buffer
    return sorted(set(result))


def signer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='antares-booking-management-v1')


def manage_token(booking):
    return signer().dumps({'id': booking.id, 'workspace_id': booking.workspace_id})


def managed(token):
    try: data = signer().loads(token, max_age=180 * 86400)
    except (BadSignature, SignatureExpired): raise APIError('Link de agendamento inválido ou expirado.', 404)
    row = Booking.query.filter_by(id=data.get('id'), workspace_id=data.get('workspace_id')).first()
    workspace = db.session.get(Workspace, row.workspace_id) if row else None
    if not row or not workspace or not workspace.active: raise APIError('Agendamento indisponível.', 404)
    return row


def slot_available(calendar, starts_at):
    return starts_at.astimezone(timezone.utc).isoformat() in availability(calendar, starts_at.astimezone(timezone_for(calendar)).date())


def reserve(calendar, data):
    # Lock the assignee before checking availability, including bookings in other calendars.
    lock('booking:' + calendar.workspace_id + ':' + str(calendar.assignee_id))
    existing = Booking.query.filter_by(calendar_id=calendar.id, submission_key=data['submission_key']).first()
    if existing: return existing
    if not slot_available(calendar, data['starts_at']): raise APIError('Este horário não está mais disponível. Escolha outro.', 409)
    email = data['email'].strip().lower()
    lock(calendar.workspace_id + ':' + email)
    contact = Contact.query.filter_by(workspace_id=calendar.workspace_id, archived=False).filter(func.lower(func.trim(Contact.email)) == email).first()
    created = contact is None
    if created:
        contact = Contact(workspace_id=calendar.workspace_id, name=data['name'].strip(), email=email, phone=data.get('phone', '').strip() or None, source='Agendamento')
        db.session.add(contact); db.session.flush()
    activity = Activity(workspace_id=calendar.workspace_id, owner_id=calendar.assignee_id, contact_id=contact.id,
        title=calendar.name[:180], kind='meeting', scheduled_at=data['starts_at'])
    db.session.add(activity); db.session.flush()
    row = Booking(workspace_id=calendar.workspace_id, calendar_id=calendar.id, contact_id=contact.id, assignee_id=calendar.assignee_id,
        activity_id=activity.id, starts_at=data['starts_at'], ends_at=data['starts_at'] + timedelta(minutes=calendar.duration_minutes),
        buffer_minutes=calendar.buffer_minutes, submission_key=data['submission_key'], consent_text=CONSENT)
    db.session.add(row); db.session.flush()
    from .automations import emit
    if created: emit(calendar.workspace_id, 'contact.created', contact.id, contact)
    emit(calendar.workspace_id, 'booking.created', row.id, contact)
    db.session.add(AuditLog(workspace_id=calendar.workspace_id, action='public_booking', resource='bookings', resource_id=row.id))
    db.session.commit()
    return row


def cancel(row):
    lock('booking:' + row.workspace_id + ':' + str(row.assignee_id))
    db.session.refresh(row)
    if row.starts_at <= now(): raise APIError('O horário deste agendamento já passou.', 409)
    if row.status != 'cancelled':
        row.status = 'cancelled'
        db.session.get(Activity, row.activity_id).status = 'cancelled'
        from .automations import emit
        emit(row.workspace_id, 'booking.cancelled', row.id, db.session.get(Contact, row.contact_id))
        db.session.add(AuditLog(workspace_id=row.workspace_id, action='cancel_booking', resource='bookings', resource_id=row.id))
        db.session.commit()
    return row


def reschedule(row, starts_at):
    lock('booking:' + row.workspace_id + ':' + str(row.assignee_id))
    db.session.refresh(row)
    if row.status != 'confirmed' or row.starts_at <= now(): raise APIError('Este agendamento não pode ser alterado.', 409)
    if row.starts_at == starts_at: return row
    calendar = published(row.calendar_id)
    # Temporarily exclude this reservation/meeting from the conflict query in the same transaction.
    activity = db.session.get(Activity, row.activity_id)
    row.status, activity.status = 'rescheduling', 'rescheduling'
    db.session.flush()
    if not slot_available(calendar, starts_at): raise APIError('Este horário não está mais disponível.', 409)
    row.starts_at, row.ends_at = starts_at, starts_at + timedelta(minutes=calendar.duration_minutes)
    row.buffer_minutes, row.status = calendar.buffer_minutes, 'confirmed'
    activity.scheduled_at, activity.status = starts_at, 'pending'
    db.session.add(AuditLog(workspace_id=row.workspace_id, action='reschedule_booking', resource='bookings', resource_id=row.id))
    db.session.commit()
    return row
