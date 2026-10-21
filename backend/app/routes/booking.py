from datetime import date, time
from flask import Blueprint, request, g
from marshmallow import fields as f, validate
from ..schemas import StrictSchema, text, ref
from ..extensions import limiter
from ..models import BookingCalendar, Booking
from ..common import require, query, page, payload, get, add, update, commit, user_ref, APIError
from ..services import booking as service
from .growth import SubmissionSchema

bp = Blueprint('booking', __name__)


class WindowSchema(StrictSchema):
    start = f.Time(required=True, format='%H:%M')
    end = f.Time(required=True, format='%H:%M')


class CalendarSchema(StrictSchema):
    name = text(150, required=True)
    description = f.String(validate=validate.Length(max=2000))
    assignee_id = ref(nullable=True)
    duration_minutes = f.Integer(validate=validate.Range(min=5, max=480))
    buffer_minutes = f.Integer(validate=validate.Range(min=0, max=120))
    lead_minutes = f.Integer(validate=validate.Range(min=0, max=43200))
    horizon_days = f.Integer(validate=validate.Range(min=1, max=180))
    availability = f.Dict(keys=f.String(validate=validate.OneOf(list('0123456'))), values=f.List(f.Nested(WindowSchema), validate=validate.Length(max=4)))
    active = f.Boolean()


class ReserveSchema(SubmissionSchema):
    starts_at = f.AwareDateTime(required=True)


class RescheduleSchema(StrictSchema):
    starts_at = f.AwareDateTime(required=True)


def validate_calendar(data):
    user_ref(data.get('assignee_id'))
    if 'availability' in data:
        for windows in data['availability'].values():
            windows.sort(key=lambda w: w['start'])
            for i, window in enumerate(windows):
                if window['start'] >= window['end'] or (i and windows[i-1]['end'] > window['start']):
                    raise APIError('Use intervalos válidos, sem sobreposição.', 422)
            for window in windows:
                window['start'], window['end'] = window['start'].strftime('%H:%M'), window['end'].strftime('%H:%M')


@bp.get('/booking-calendars')
@require()
def calendars(): return page(query(BookingCalendar).order_by(BookingCalendar.name))


@bp.post('/booking-calendars')
@require('owner', 'admin')
def create_calendar():
    data = payload(CalendarSchema); validate_calendar(data)
    return commit(add(BookingCalendar, data), 201)


@bp.patch('/booking-calendars/<uuid:calendar_id>')
@require('owner', 'admin')
def edit_calendar(calendar_id):
    row = get(BookingCalendar, calendar_id)
    data = payload(CalendarSchema, partial=True); validate_calendar(data)
    update(row, data)
    return commit(row)


@bp.get('/bookings')
@require()
def bookings(): return page(query(Booking).order_by(Booking.starts_at.desc()))


@bp.get('/public/calendars/<uuid:calendar_id>')
@limiter.limit('120 per minute')
def public_calendar(calendar_id): return service.public_copy(service.published(calendar_id))


@bp.get('/public/calendars/<uuid:calendar_id>/slots')
@limiter.limit('120 per minute')
def slots(calendar_id):
    calendar = service.published(calendar_id)
    try: day = date.fromisoformat(request.args.get('date', ''))
    except ValueError: raise APIError('Informe uma data válida.', 422)
    return {'items': service.availability(calendar, day), 'timezone': str(service.timezone_for(calendar))}


@bp.post('/public/calendars/<uuid:calendar_id>/book')
@limiter.limit('10 per minute;100 per hour')
def book(calendar_id):
    if request.content_length and request.content_length > 8192: raise APIError('Solicitação muito grande.', 413)
    data = payload(ReserveSchema)
    row = service.reserve(service.published(calendar_id), data)
    return {'message': 'Agendamento confirmado.', 'token': service.manage_token(row)}, 200


@bp.get('/public/bookings/<token>')
@limiter.limit('60 per minute')
def manage(token):
    row = service.managed(token)
    calendar = BookingCalendar.query.filter_by(id=row.calendar_id, workspace_id=row.workspace_id).first()
    return {'name': calendar.name, 'starts_at': row.starts_at.isoformat(), 'status': row.status,
            'calendar_id': calendar.id, 'timezone': str(service.timezone_for(calendar))}


@bp.post('/public/bookings/<token>/cancel')
@limiter.limit('10 per minute')
def cancel(token):
    service.cancel(service.managed(token))
    return {'message': 'Agendamento cancelado.'}


@bp.post('/public/bookings/<token>/reschedule')
@limiter.limit('10 per minute')
def reschedule(token):
    data = payload(RescheduleSchema)
    service.reschedule(service.managed(token), data['starts_at'])
    return {'message': 'Agendamento alterado.'}
