"""
SQL lives in the .sql files next to this module. Each file may use two
placeholders that are filled with trusted, code-generated fragments:

    {metrics}  the shared measure definitions below
    {where}    the WHERE clause compiled by filters.Filters

All user-supplied values are bound parameters, never interpolated.
"""
from __future__ import annotations

from ..db import load_sql

# Ratio-of-sums, never mean-of-means: a zone with 3 trips must not weigh the
# same as one with 30 000. avg_speed is distance-weighted (total miles / total
# hours), i.e. the speed of the network, not of the average trip.
METRICS = """
    SUM(trips)                                              AS trips,
    ROUND(SUM(sum_total), 2)                                AS revenue,
    ROUND(SUM(sum_fare)     / SUM(trips), 2)                AS avg_fare,
    ROUND(SUM(sum_distance) / SUM(trips), 2)                AS avg_distance,
    ROUND(SUM(sum_duration) / SUM(trips), 1)                AS avg_duration,
    ROUND(SUM(sum_distance) / (SUM(sum_duration) / 60.0), 2) AS avg_speed,
    ROUND(SUM(sum_fare)     / SUM(sum_distance), 2)         AS fare_per_mile,
    ROUND(SUM(sum_tip_pct)  / NULLIF(SUM(card_trips), 0), 1) AS tip_pct,
    ROUND(100.0 * SUM(airport_trips)    / SUM(trips), 2)    AS airport_share,
    ROUND(100.0 * SUM(cross_boro_trips) / SUM(trips), 2)    AS cross_borough_share,
    ROUND(100.0 * SUM(card_trips)       / SUM(trips), 1)    AS card_share
"""

OD_METRICS = """
    SUM(trips)                                               AS trips,
    ROUND(SUM(sum_fare)     / SUM(trips), 2)                 AS avg_fare,
    ROUND(SUM(sum_distance) / SUM(trips), 2)                 AS avg_distance,
    ROUND(SUM(sum_duration) / SUM(trips), 1)                 AS avg_duration,
    ROUND(SUM(sum_distance) / (SUM(sum_duration) / 60.0), 2) AS avg_speed,
    ROUND(SUM(sum_detour)   / NULLIF(SUM(detour_trips), 0), 3) AS detour_index
"""


def render(name: str, where: str = "", **extra) -> str:
    return load_sql(name).format(metrics=METRICS, od_metrics=OD_METRICS, where=where, **extra)
