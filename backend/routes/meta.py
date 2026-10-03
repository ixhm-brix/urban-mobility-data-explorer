"""Reference data the dashboard needs to build its filter controls."""
from flask import Blueprint

from backend.db import query, query_one
from backend.routes._common import ok

bp = Blueprint("meta", __name__)


@bp.get("/api/meta")
def meta():
    return ok({
        "date_range": query_one("SELECT MIN(pickup_date) AS min, MAX(pickup_date) AS max FROM agg_zone_hour"),
        "boroughs": query("""SELECT b.borough_id AS id, b.name, COUNT(z.location_id) AS zones
                             FROM boroughs b JOIN zones z USING (borough_id)
                             GROUP BY b.borough_id ORDER BY b.name"""),
        "zones": query("""SELECT z.location_id AS id, z.zone_name AS name, z.borough_id, b.name AS borough
                          FROM zones z JOIN boroughs b USING (borough_id) ORDER BY z.zone_name"""),
        "payment_types": query("SELECT payment_type_id AS id, description AS name FROM payment_types ORDER BY id"),
        "distance_bands": query("SELECT distance_band_id AS id, label AS name, min_mi, max_mi FROM distance_bands ORDER BY id"),
        "fare_bands": query("SELECT fare_band_id AS id, label AS name, min_usd, max_usd FROM fare_bands ORDER BY id"),
        "time_bands": query("SELECT band AS name, MIN(hour) AS hour_from, MAX(hour) AS hour_to FROM time_bands GROUP BY band ORDER BY MIN(band_order)"),
        "run": query_one("SELECT * FROM data_quality_run ORDER BY run_id DESC LIMIT 1"),
    })


@bp.get("/api/health")
def health():
    return ok({"status": "ok", "trips": query_one("SELECT SUM(trips) AS n FROM agg_zone_hour")["n"]})
