from marshmallow import fields as f
from marshmallow import pre_load, validate

from ..services.conditions import ConditionsSchema
from ..services.form_design import DesignSchema, SettingsSchema
from ..services.form_fields import FormFieldSchema
from .base import StrictSchema, choice, ref, text

CONSENT = 'Autorizo o contato em resposta a esta solicitação.'


class FormSchema(StrictSchema):
    fields = f.List(f.Nested(FormFieldSchema), validate=validate.Length(max=60))
    brand_name = f.String(validate=validate.Length(max=120))
    design = f.Nested(DesignSchema)
    settings = f.Nested(SettingsSchema)
    accent_color = f.String(validate=validate.Regexp(r'^#[0-9a-fA-F]{6}$'))
    name = text(150, required=True)
    headline = text(180, required=True)
    description = f.String(validate=validate.Length(max=2000))
    success_message = text(500)
    stage_id = ref(required=True)
    source = text(100)
    active = f.Boolean()

    @pre_load
    def clear_description(self, data, **kwargs):
        # The shared editor sends null when an optional field is cleared.
        if isinstance(data, dict) and data.get('description', '') is None:
            return {**data, 'description': ''}
        return data


class SubmissionSchema(StrictSchema):
    answers = f.Dict(keys=f.String(), values=f.Raw(), load_default=dict, validate=validate.Length(max=60))
    attribution = f.Dict(
        keys=f.String(
            validate=validate.OneOf(
                [
                    'utm_source',
                    'utm_medium',
                    'utm_campaign',
                    'utm_content',
                    'utm_term',
                    'funnel_id',
                    'funnel_step_id',
                    'visitor_id',
                ]
            )
        ),
        values=f.String(validate=validate.Length(max=300)),
        load_default=dict,
    )
    submission_key = ref(required=True)
    name = text(180, required=True)
    email = f.Email(required=True, validate=validate.Length(max=254))
    phone = f.String(validate=validate.Length(max=30), load_default='')
    consent = f.Boolean(required=True, validate=validate.Equal(True))
    website = f.String(validate=validate.Length(max=0), load_default='')  # Honeypot, not the lead's website.

    @pre_load
    def normalize_email(self, data, **kwargs):
        if isinstance(data, dict) and isinstance(data.get('email'), str):
            return {**data, 'email': data['email'].strip().lower()}
        return data


class OffsetSchema(StrictSchema):
    """How far the user dragged a card from its automatic place on the editor canvas."""

    x = f.Integer(required=True, validate=validate.Range(min=-20000, max=20000))
    y = f.Integer(required=True, validate=validate.Range(min=-20000, max=20000))


class LinkButtonSchema(StrictSchema):
    """An Instagram button that opens a web page inside the app."""

    title = text(20, required=True)
    url = f.Url(required=True, schemes={'https'}, validate=validate.Length(max=1000))


class ActionSchema(StrictSchema):
    conditions = f.Nested(ConditionsSchema)
    kind = choice(
        'create_task send_message follow_up add_tag move_stage reply_comment private_reply instagram_message atlas_assign branch',
        required=True,
    )
    title = text(180)
    content = text(1000)
    atlas_channel = choice('whatsapp instagram')
    template_id = ref()
    tag = text(80)
    stage_id = ref()
    delay_minutes = f.Integer(validate=validate.Range(min=0, max=525600), load_default=0)
    due_days = f.Integer(validate=validate.Range(min=0, max=365), load_default=0)
    # A branch splits the flow: `yes` runs when its conditions match, `no` otherwise.
    yes = f.List(f.Nested(lambda: ActionSchema()), validate=validate.Length(max=10))
    no = f.List(f.Nested(lambda: ActionSchema()), validate=validate.Length(max=10))
    offset = f.Nested(OffsetSchema)
    # Instagram only: up to 3 link buttons, and up to 13 quick replies whose tap comes back as the contact's message.
    buttons = f.List(f.Nested(LinkButtonSchema), validate=validate.Length(max=3))
    quick_replies = f.List(text(20), validate=validate.Length(max=13))


class RuleSchema(StrictSchema):
    conditions = f.Nested(ConditionsSchema)
    stop_on_reply = f.Boolean()
    required_tag = text(80, allow_none=True)
    actions = f.List(f.Nested(ActionSchema), validate=validate.Length(max=10))
    name = text(150, required=True)
    event = choice(
        'contact.created form.submitted message.received booking.created booking.cancelled opportunity.created instagram.comment opportunity.stage_changed opportunity.won opportunity.lost atlas.handoff',
        required=True,
    )
    source = text(100, allow_none=True)
    task_title = text(180, required=True)
    due_days = f.Integer(validate=validate.Range(min=0, max=365))
    assignee_id = ref(nullable=True)
    active = f.Boolean()
