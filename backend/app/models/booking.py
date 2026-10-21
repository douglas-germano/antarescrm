from sqlalchemy import CheckConstraint, UniqueConstraint

from ..extensions import db
from .base import TenantBase, UTCDateTime


class BookingCalendar(TenantBase):
    __tablename__ = 'booking_calendars'
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.String(2000), nullable=False, default='')
    assignee_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    duration_minutes = db.Column(db.Integer, nullable=False, default=30)
    buffer_minutes = db.Column(db.Integer, nullable=False, default=0)
    lead_minutes = db.Column(db.Integer, nullable=False, default=120)
    horizon_days = db.Column(db.Integer, nullable=False, default=60)
    availability = db.Column(
        db.JSON, nullable=False, default=lambda: {str(i): [{'start': '09:00', 'end': '18:00'}] for i in range(5)}
    )
    active = db.Column(db.Boolean, nullable=False, default=False)


class Booking(TenantBase):
    __tablename__ = 'bookings'
    calendar_id = db.Column(db.String(36), db.ForeignKey('booking_calendars.id'), nullable=False, index=True)
    contact_id = db.Column(db.String(36), db.ForeignKey('contacts.id'), nullable=False)
    assignee_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    activity_id = db.Column(db.String(36), db.ForeignKey('activities.id'), nullable=False)
    starts_at = db.Column(UTCDateTime(), nullable=False, index=True)
    ends_at = db.Column(UTCDateTime(), nullable=False)
    buffer_minutes = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default='confirmed')
    submission_key = db.Column(db.String(36), nullable=False)
    consent_text = db.Column(db.String(255), nullable=False)
    __table_args__ = (UniqueConstraint('calendar_id', 'submission_key'), CheckConstraint('ends_at > starts_at'))
