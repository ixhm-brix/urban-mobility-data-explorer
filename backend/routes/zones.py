"""Spatial endpoints: polygons, per-zone metrics, rankings and a zone's profile."""
import json
from dataclasses import replace

from flask import Blueprint, abort, request

from algorithms.top_k_heap import top_k
from backend.db import query, query_one
from backend.queries import render
from backend.queries.filters import FilterError
from backend.routes._common import filters, ok

bp = Blueprint("zones", __name__)

ZONE_METRICS = {"trips", "revenue", "avg_fare", "avg_distance", "avg_duration", "avg_speed",
                "fare_per_mile", "tip_pct", "airport_share", "cross_borough_share"}
_geojson_cache: dict = {}


@bp.get("/api/zones/geojson")
def geojson():
    if "fc" not in _geojson_cache:
        features = [{
            "type": "Feature",
            "id": r["location_id"],
            "properties": {k: r[k] for k in ("location_id", "zone", "borough", "service_zone")},
            "geometry": json.loads(r["geojson"]),
        } for r in query(render("geojson"))]
        _geojson_cache["fc"] = {"type": "FeatureCollection", "features": features}
    return ok(_geojson_cache["fc"])


@bp.get("/api/zones/metrics")
def zone_metrics():
    f = filters()
    where, params = f.where("agg", alias="a")
    return ok(query(render("zone_metrics", where), params), f)


@bp.get("/api/zones/rank")
def zone_rank():
    """Top / bottom K zones on any metric — ranked with the custom heap, not ORDER BY."""
    f = filters()
    metric = request.args.get("metric", "trips")
    if metric not in ZONE_METRICS:
        raise FilterError(f"metric must be one of {sorted(ZONE_METRICS)}")
    k = _k(request.args.get("k"), 10)
    order = request.args.get("order", "desc")
    min_trips = _k(request.args.get("min_trips"), 100, hi=100000)
    where, params = f.where("agg", alias="a")
    rows = [r for r in query(render("zone_metrics", where), params) if r["trips"] >= min_trips]
    ranked = top_k(rows, k, lambda r: r[metric], largest=(order != "asc"))
    return ok(ranked, f, metric=metric, candidates=len(rows), algorithm="top_k_heap")


@bp.get("/api/zones/<int:location_id>")
def zone_detail(location_id: int):
    info = query_one(render("zone_info"), [location_id])
    if not info:
        abort(404, description=f"zone {location_id} not found")
    f = filters()
    f.zone, f.borough = location_id, None                   # the zone overrides area filters
    where, params = f.where("agg")
    metrics = query_one(render("summary", where), params)
    where_a, params_a = f.where("agg", alias="a")
    hourly = query(render("hourly", where_a), params_a)
    # Flows: the {side} predicate pins the zone, the rest of the filters ride along.
    od_where, od_params = replace(f, zone=None).where("od", alias="o")
    extra = "AND " + od_where[len("WHERE "):] if od_where else ""
    dests = query(render("zone_flows", side="pu", other="do", extra=extra), [location_id] + od_params)
    origins = query(render("zone_flows", side="do", other="pu", extra=extra), [location_id] + od_params)
    return ok({
        "zone": info,
        "metrics": metrics,
        "hourly": hourly,
        "top_destinations": top_k(dests, 8, lambda r: r["trips"]),
        "top_origins": top_k(origins, 8, lambda r: r["trips"]),
    }, f)


def _k(v, default, hi=100):
    if v in (None, ""):
        return default
    try:
        n = int(v)
    except ValueError as exc:
        raise FilterError("k must be an integer") from exc
    return max(1, min(n, hi))
