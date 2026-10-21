"""Client projects API: stages, projects, files and approvals."""

from flask import Blueprint

bp = Blueprint('projects', __name__)

from . import stages, crud, files, approvals  # noqa: E402,F401
