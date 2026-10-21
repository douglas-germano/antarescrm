"""Lead forms, automation rules, runs and the job queue API."""

from flask import Blueprint

bp = Blueprint('growth', __name__)

from . import automations, forms, jobs  # noqa: E402,F401
