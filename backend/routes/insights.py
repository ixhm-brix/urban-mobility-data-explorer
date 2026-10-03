from flask import Blueprint

from algorithms.insights import all_insights
from backend.routes._common import filters, ok

bp = Blueprint("insights", __name__)


@bp.get("/api/insights")
def insights():
    f = filters()
    return ok(all_insights(f), f)
