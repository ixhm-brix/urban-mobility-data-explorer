"""Publishes the cleaning log so the dashboard is transparent about what was removed."""
from flask import Blueprint

from backend.db import query, query_one
from backend.queries import render
from backend.routes._common import ok

bp = Blueprint("quality", __name__)


@bp.get("/api/quality")
def quality():
    return ok({
        "run": query_one("SELECT * FROM data_quality_run ORDER BY run_id DESC LIMIT 1"),
        "rules": query(render("quality")),
    })
