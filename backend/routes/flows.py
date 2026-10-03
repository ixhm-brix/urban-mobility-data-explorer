"""Origin -> destination analysis over agg_od."""
from flask import Blueprint, request

from algorithms.top_k_heap import top_k
from backend.db import query
from backend.queries import render
from backend.queries.filters import FilterError
from backend.routes._common import filters, ok
from backend.routes.zones import _k

bp = Blueprint("flows", __name__)

ROUTE_METRICS = {"trips", "avg_fare", "avg_distance", "avg_duration", "avg_speed", "detour_index"}


@bp.get("/api/routes/top")
def top_routes():
    """Rank O->D pairs. SQL aggregates; algorithms/top_k_heap.py picks the K best."""
    f = filters()
    by = request.args.get("by", "trips")
    if by not in ROUTE_METRICS:
        raise FilterError(f"by must be one of {sorted(ROUTE_METRICS)}")
    order = request.args.get("order", "desc")
    k = _k(request.args.get("k"), 10, hi=50)
    # Averages on a handful of trips are noise; require volume unless ranking by volume.
    min_trips = _k(request.args.get("min_trips"), 1 if by == "trips" else 50, hi=100000)
    include_same = request.args.get("same_zone", "0") == "1"
    where, params = f.where("od", alias="o")
    rows = query(render("routes", where), params + [min_trips])
    if not include_same:
        rows = [r for r in rows if r["pu_id"] != r["do_id"]]
    ranked = top_k(rows, k, lambda r: r[by], largest=(order != "asc"))
    names = {z["id"]: z for z in query(
        "SELECT z.location_id AS id, z.zone_name AS zone, b.name AS borough "
        "FROM zones z JOIN boroughs b USING (borough_id)")}
    for r in ranked:
        r["pu_zone"], r["pu_borough"] = names[r["pu_id"]]["zone"], names[r["pu_id"]]["borough"]
        r["do_zone"], r["do_borough"] = names[r["do_id"]]["zone"], names[r["do_id"]]["borough"]
    return ok(ranked, f, target="od", by=by, candidates=len(rows), algorithm="top_k_heap",
              partial_days=f.od_is_partial())


@bp.get("/api/flows/boroughs")
def borough_flows():
    f = filters()
    where, params = f.where("od", alias="o")
    return ok(query(render("borough_flows", where), params), f, target="od",
              partial_days=f.od_is_partial())
