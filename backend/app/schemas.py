from decimal import Decimal
from marshmallow import Schema, fields as f, validate, RAISE


def text(length=180, **kw):
    return f.String(validate=[validate.Length(min=1, max=length), validate.Regexp(r'\S', error='Informe um texto válido.')], **kw)


def choice(options, **kw):
    return f.String(validate=validate.OneOf(options.split()), **kw)


def money(required=False, zero=False):
    return f.Decimal(places=2, as_string=True, required=required, allow_nan=False,
                     validate=validate.Range(min=Decimal('0') if zero else Decimal('0.01'), max=Decimal('999999999999.99')))


def ref(required=False, nullable=False):
    return f.UUID(required=required, allow_none=nullable)


class StrictSchema(Schema):
    class Meta:
        unknown = RAISE


class RegisterSchema(StrictSchema):
    workspace_name = text(150, required=True)
    slug = f.String(required=True, validate=validate.Regexp(r'^[a-z0-9][a-z0-9-]{2,79}$'))
    name = text(150, required=True)
    email = f.Email(required=True, validate=validate.Length(max=254))
    password = f.String(required=True, load_only=True, validate=validate.Length(min=10, max=128))


class LoginSchema(StrictSchema):
    slug = text(80, required=True)
    email = f.Email(required=True)
    password = text(128, required=True, load_only=True)


class UserSchema(StrictSchema):
    name = text(150, required=True)
    email = f.Email(required=True)
    password = f.String(required=True, load_only=True, validate=validate.Length(min=10, max=128))
    role = choice('admin member')
    title = text(80, allow_none=True)
    active = f.Boolean()


class UserUpdateSchema(StrictSchema):
    name = text(150)
    role = choice('admin member')
    title = text(80, allow_none=True)
    active = f.Boolean()
    password = f.String(load_only=True, validate=validate.Length(min=10, max=128))


class ProfileSchema(StrictSchema):
    name = text(150)
    title = text(80, allow_none=True)
    current_password = f.String(load_only=True, validate=validate.Length(max=128))
    password = f.String(load_only=True, validate=validate.Length(min=10, max=128))


class WorkspaceSchema(StrictSchema):
    name = text(150)
    timezone = text(80)


class RecordSchema(StrictSchema):
    tags = f.List(text(80), validate=validate.Length(max=50))
    custom_fields = f.Dict(keys=text(80), values=f.String(validate=validate.Length(max=2000)), validate=validate.Length(max=50))


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
