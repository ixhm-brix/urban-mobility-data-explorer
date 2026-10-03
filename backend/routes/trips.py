"""Trip-level explorer: filtered, sorted, paginated rows and single-trip detail."""
from flask import Blueprint, abort, request

from backend.db import query, query_one
from backend.queries import render
from backend.queries.filters import FilterError
from backend.routes._common import filters, ok

bp = Blueprint("trips", __name__)

# Whitelisted sort keys -> indexed columns (see database/schema.sql).
SORTS = {
    "pickup": "t.pickup_datetime",
    "distance": "t.trip_distance",
    "fare": "t.fare_amount",
    "duration": "t.trip_duration_min",
    "speed": "t.avg_speed_mph",
}
MAX_PAGE_SIZE = 100


@bp.get("/api/trips")
def trips():
    f = filters()
    sort = request.args.get("sort", "pickup")
    if sort not in SORTS:
        raise FilterError(f"sort must be one of {sorted(SORTS)}")
    direction = "ASC" if request.args.get("order", "desc").lower() == "asc" else "DESC"
    try:
        page = max(1, int(request.args.get("page", 1)))
        size = min(MAX_PAGE_SIZE, max(1, int(request.args.get("page_size", 25))))
    except ValueError as exc:
        raise FilterError("page and page_size must be integers") from exc

    # Exact total from the roll-up — the filters map 1:1, and it avoids a 7.6 M-row COUNT(*).
    agg_where, agg_params = f.where("agg")
    total = query_one(f"SELECT SUM(trips) AS n FROM agg_zone_hour {agg_where}", agg_params)["n"] or 0

    # Plan choice for a borough filter: if the borough holds a large share of trips,
    # walking the sort index finds 25 matches almost at once; if it is small (Staten
    # Island, EWR) the zone index is faster. The roll-up tells us which case we're in.
    scan_area = False
    if f.borough is not None and f.zone is None:
        share = query_one("""SELECT 1.0 * SUM(CASE WHEN z.borough_id = ? THEN a.trips END) / SUM(a.trips) AS s
                             FROM agg_zone_hour a JOIN zones z ON z.location_id = a.pu_location_id""",
                          [f.borough])["s"] or 0
        scan_area = share >= 0.05

    where, params = f.where("trips", alias="t", scan_area=scan_area)
    order = f"{SORTS[sort]} {direction}, t.trip_id {direction}"
    rows = query(render("trips_page", where, order=order), params + [size, (page - 1) * size])
    return ok(rows, f, target="trips", page=page, page_size=size, total=total,
              pages=(total + size - 1) // size, sort=sort, order=direction.lower())


@bp.get("/api/trips/<int:trip_id>")
def trip_detail(trip_id: int):
    row = query_one(render("trip_detail"), [trip_id])
    if not row:
        abort(404, description=f"trip {trip_id} not found")
    # Context: how this trip compares with the same route at the same hour.
    peers = query_one("""
        SELECT SUM(trips) AS trips,
               ROUND(SUM(sum_fare) / SUM(trips), 2) AS avg_fare,
               ROUND(SUM(sum_duration) / SUM(trips), 1) AS avg_duration,
               ROUND(SUM(sum_distance) / (SUM(sum_duration) / 60.0), 2) AS avg_speed
        FROM agg_od
        WHERE pu_location_id = ? AND do_location_id = ? AND pickup_hour = ? AND is_weekend = ?""",
        [row["pu_location_id"], row["do_location_id"], row["pickup_hour"], row["is_weekend"]])
    return ok({"trip": row, "route_peers": peers})
