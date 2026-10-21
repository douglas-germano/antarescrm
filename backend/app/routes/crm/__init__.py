"""CRM core API: companies, contacts, pipelines, opportunities, activities and CSV import/export."""

from flask import Blueprint

bp = Blueprint('crm', __name__)

from ._search import fold  # noqa: E402,F401  (re-exported for callers and tests)
from . import companies, contacts, pipeline, opportunities, activities, csv_io  # noqa: E402,F401
