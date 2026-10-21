from marshmallow import fields as f
from marshmallow import validate

from .base import StrictSchema, choice, money, ref, text


class ProjectStageSchema(StrictSchema):
    name = text(80, required=True)
    position = f.Integer(validate=validate.Range(min=0, max=1000))
    color = f.String(validate=validate.Regexp(r'^#[0-9a-fA-F]{6}$'))
    is_final = f.Boolean()


class ProjectSchema(StrictSchema):
    title = text(180, required=True)
    description = text(5000, allow_none=True)
    contact_id = ref(nullable=True)
    company_id = ref(nullable=True)
    opportunity_id = ref(nullable=True)
    owner_id = ref(nullable=True)
    stage_id = ref()
    amount = money(zero=True)
    status = choice('active done cancelled')
    start_date = f.Date(allow_none=True)
    due_date = f.Date(allow_none=True)


class NoteSchema(StrictSchema):
    text = text(500, required=True)


class ApprovalSchema(StrictSchema):
    file_id = ref(nullable=True)
    title = text(180, required=True)
    message = text(2000, allow_none=True)
    channel = choice('public internal', load_default='public')
    expires_days = f.Integer(validate=validate.Range(min=1, max=180), load_default=30)


class DecisionSchema(StrictSchema):
    decision = choice('approved changes_requested', required=True)
    name = text(150, required=True)
    comment = text(2000, allow_none=True)


class FileMetaSchema(StrictSchema):
    title = text(180)
    kind = choice('layout document other')
    note = text(2000, allow_none=True)
