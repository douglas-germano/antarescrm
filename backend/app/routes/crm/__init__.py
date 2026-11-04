"""CRM core API: companies, contacts, pipelines, opportunities, activities and CSV import/export."""

from flask import Blueprint

bp = Blueprint('crm', __name__)

from . import activities, companies, contacts, csv_io, opportunities, pipeline  # noqa: E402,F401
from ._search import fold  # noqa: E402,F401  (re-exported for callers and tests)
