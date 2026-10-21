"""Marshmallow schemas por domínio; reexportados aqui para `from app.schemas import X`."""

from .auth import LoginSchema, ProfileSchema, RegisterSchema, UserSchema, UserUpdateSchema, WorkspaceSchema
from .base import StrictSchema, choice, money, ref, text
from .crm import (
    ActivitySchema,
    CloseSchema,
    CompanySchema,
    ContactSchema,
    OpportunitySchema,
    RecordSchema,
    StageSchema,
    TaskSchema,
)
from .projects import ApprovalSchema, DecisionSchema, FileMetaSchema, NoteSchema, ProjectSchema, ProjectStageSchema
