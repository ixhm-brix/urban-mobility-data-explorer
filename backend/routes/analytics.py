"""Aggregate views over agg_zone_hour: KPIs, time profiles and breakdowns."""
from flask import Blueprint

from backend.db import query, query_one
from backend.queries import render
from backend.routes._common import filters, ok

bp = Blueprint("analytics", __name__)


@bp.get("/api/summary")
def summary():
    f = filters()
    where, params = f.where("agg")
    current = query_one(render("summary", where), params)
    # The unfiltered month, so every KPI can show how the selection compares.
    baseline = query_one(render("summary"))
    return ok({"current": current, "baseline": baseline}, f)


@bp.get("/api/timeseries/daily")
def daily():
    f = filters()
    where, params = f.where("agg")
    return ok(query(render("daily", where), params), f)


@bp.get("/api/timeseries/hourly")
def hourly():
    f = filters()
    where, params = f.where("agg", alias="a")
    return ok(query(render("hourly", where), params), f)


@bp.get("/api/heatmap")
def heatmap():
    f = filters()
    where, params = f.where("agg")
    return ok(query(render("heatmap", where), params), f)


@bp.get("/api/breakdown/distance")
def by_distance():
    f = filters()
    where, params = f.where("agg", alias="a")
    return ok(query(render("distance_bands", where), params), f)


@bp.get("/api/breakdown/payment")
def by_payment():
    f = filters()
    where, params = f.where("agg", alias="a")
    return ok(query(render("payment_mix", where), params), f)
