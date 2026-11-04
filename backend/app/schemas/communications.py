"""Request contracts for templates, inbox operations and signed deliveries."""

from marshmallow import fields as f
from marshmallow import validate

from .base import StrictSchema, choice, ref, text
from .crm import OpportunitySchema


class TemplateSchema(StrictSchema):
    name = text(150, required=True)
    channel = choice('email sms whatsapp', required=True)
    subject = f.String(validate=validate.Length(max=180), load_default='')
    content = text(20000, required=True)


class SendSchema(StrictSchema):
    contact_ids = f.List(ref(required=True), required=True, validate=validate.Length(min=1, max=100))
    template_id = ref(required=True)
    idempotency_key = ref(required=True)


class ReceiveSchema(StrictSchema):
    provider_id = text(100, required=True)
    address = text(254, required=True)
    content = text(20000, required=True)
    subject = f.String(validate=validate.Length(max=180), load_default='')


class ReplySchema(StrictSchema):
    content = text(20000, required=True)
    idempotency_key = ref(required=True)


class InboxContactSchema(StrictSchema):
    name = text(required=True)
    email = f.Email(allow_none=True, validate=validate.Length(max=254))
    phone = text(30, allow_none=True)


class InboxOpportunitySchema(OpportunitySchema):
    idempotency_key = ref(required=True)
    contact = f.Nested(InboxContactSchema)


class ThreadUpdate(StrictSchema):
    status = choice('open closed')
    assigned_to_id = ref(nullable=True)


class NotificationReadSchema(StrictSchema):
    source = choice('whatsapp inbox', required=True)
    thread_id = ref(required=True)
    message_id = ref(required=True)


class WhatsAppSendSchema(StrictSchema):
    content = text(20000, required=True)
    idempotency_key = text(100, required=True)
