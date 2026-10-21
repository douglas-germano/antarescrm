from marshmallow import fields as f
from marshmallow import validate

from .base import StrictSchema, choice, text


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
