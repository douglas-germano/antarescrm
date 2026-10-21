from marshmallow import fields as f
from marshmallow import validate

from .base import StrictSchema, choice, money, ref, text


class RecordSchema(StrictSchema):
    tags = f.List(text(80), validate=validate.Length(max=50))
    custom_fields = f.Dict(
        keys=text(80), values=f.String(validate=validate.Length(max=2000)), validate=validate.Length(max=50)
    )


class CompanySchema(RecordSchema):
    name = text(required=True)
    document = text(20, allow_none=True)
    website = text(255, allow_none=True)
    email = f.Email(allow_none=True)
    phone = text(30, allow_none=True)
    industry = text(120, allow_none=True)
    address = text(2000, allow_none=True)
    notes = text(5000, allow_none=True)


class ContactSchema(RecordSchema):
    name = text(required=True)
    company_id = ref(nullable=True)
    owner_id = ref(nullable=True)
    email = f.Email(allow_none=True)
    phone = text(30, allow_none=True)
    position = text(120, allow_none=True)
    source = text(100, allow_none=True)
    notes = text(5000, allow_none=True)


class StageSchema(StrictSchema):
    pipeline_id = ref(nullable=True)
    name = text(80, required=True)
    position = f.Integer(validate=validate.Range(min=0, max=10000))
    color = f.String(validate=validate.Regexp(r'^#[0-9a-fA-F]{6}$'))
    probability = f.Integer(allow_none=True, validate=validate.Range(min=0, max=100))


class OpportunitySchema(StrictSchema):
    contact_id = ref(nullable=True)
    company_id = ref(nullable=True)
    stage_id = ref(required=True)
    owner_id = ref(nullable=True)
    title = text(required=True)
    description = text(5000, allow_none=True)
    amount = money(zero=True)
    expected_close_date = f.Date(allow_none=True)


class CloseSchema(StrictSchema):
    status = choice('won lost', required=True)
    loss_reason = text(2000, allow_none=True)


class ActivitySchema(StrictSchema):
    title = text(required=True)
    kind = choice('follow_up call meeting email note')
    opportunity_id = ref(nullable=True)
    contact_id = ref(nullable=True)
    company_id = ref(nullable=True)
    owner_id = ref(nullable=True)
    scheduled_at = f.AwareDateTime(required=True)
    status = choice('pending completed cancelled')
    notes = text(5000, allow_none=True)


class TaskSchema(StrictSchema):
    title = text(required=True)
    description = text(5000, allow_none=True)
    assignee_id = ref(nullable=True)
    contact_id = ref(nullable=True)
    company_id = ref(nullable=True)
    opportunity_id = ref(nullable=True)
    status = choice('todo doing done cancelled')
    priority = choice('low medium high urgent')
    due_date = f.Date(allow_none=True)
