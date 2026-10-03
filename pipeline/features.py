"""
Stage 3 — Feature engineering.

Four derived features, each combining several raw columns to answer a question
the raw columns cannot answer alone:

1. avg_speed_mph   = trip_distance / duration
   Congestion proxy. Distance and time on their own conflate "long trip" with
   "slow trip"; speed separates them, so we can see *when* and *where* the city
   jams (e.g. Midtown at 5 pm vs. 5 am).

2. fare_per_mile   = fare_amount / trip_distance
   Price efficiency for the rider and revenue efficiency for the driver.
   Because the meter charges for both distance and waiting time, $/mile rises
   in congestion — it reveals the hidden "traffic tax" per zone and hour.

3. tip_pct         = tip_amount / fare_amount × 100   (card payments only)
   Rider generosity / satisfaction. Cash tips are not recorded by the meter,
   so including cash trips would bias tips to 0; we set it to NULL for them.

4. detour_index    = trip_distance / straight-line distance between zone centroids
   Route circuity. ≈1.3 is typical for a street grid; high values flag trips
   forced around rivers, bridges and highway access (or circuitous routing).
   Only defined when pickup ≠ dropoff zone and both zones are mapped.

Supporting temporal / categorical keys (cheap to index, used by every filter):
pickup_date, pickup_hour, pickup_dow, is_weekend, time_band,
trip_duration_min, is_airport_trip, is_cross_borough, distance_band_id, fare_band_id.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

AIRPORT_ZONES = {1, 132, 138}   # Newark (EWR), JFK, LaGuardia

# (id, label, lower bound inclusive, upper bound exclusive). Single source of truth:
# database/load_data.py imports these to fill the band dimension tables.
DISTANCE_BANDS = [(1, "Under 1 mi", 0, 1), (2, "1–2 mi", 1, 2), (3, "2–5 mi", 2, 5),
                  (4, "5–10 mi", 5, 10), (5, "10–20 mi", 10, 20), (6, "20+ mi", 20, 1000)]
FARE_BANDS = [(1, "Under $10", 0, 10), (2, "$10–20", 10, 20), (3, "$20–40", 20, 40),
              (4, "$40–70", 40, 70), (5, "$70+", 70, 100000)]


def band(values: pd.Series, bands) -> pd.Series:
    edges = [b[2] for b in bands] + [bands[-1][3]]
    return pd.cut(values, bins=edges, labels=[b[0] for b in bands], right=False).astype("int8")


def time_band(hour: pd.Series) -> pd.Series:
    bins = [-1, 5, 9, 15, 19, 23]
    labels = ["Overnight", "Morning peak", "Midday", "Evening peak", "Night"]
    return pd.cut(hour, bins=bins, labels=labels).astype(str)


def _haversine_mi(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    h = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 3958.7613 * np.arcsin(np.sqrt(h))


def add_features(df: pd.DataFrame, zones: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    pu, do = out["tpep_pickup_datetime"], out["tpep_dropoff_datetime"]

    out["trip_duration_min"] = ((do - pu).dt.total_seconds() / 60).round(2)
    out["pickup_date"] = pu.dt.strftime("%Y-%m-%d")
    out["pickup_hour"] = pu.dt.hour.astype("int8")
    out["pickup_dow"] = pu.dt.dayofweek.astype("int8")        # 0 = Monday
    out["is_weekend"] = (out["pickup_dow"] >= 5).astype("int8")
    out["time_band"] = time_band(out["pickup_hour"])

    # 1. speed
    out["avg_speed_mph"] = (out["trip_distance"] / (out["trip_duration_min"] / 60)).round(2)
    # 2. price per mile
    out["fare_per_mile"] = (out["fare_amount"] / out["trip_distance"]).round(2)
    # 3. tip share, card only
    card = out["payment_type"] == 1
    out["tip_pct"] = np.where(card, (100 * out["tip_amount"] / out["fare_amount"]).round(2), np.nan)

    # 4. detour index via zone centroids
    z = zones.set_index("location_id")
    lon1 = out["PULocationID"].map(z["centroid_lon"]).astype(float)
    lat1 = out["PULocationID"].map(z["centroid_lat"]).astype(float)
    lon2 = out["DOLocationID"].map(z["centroid_lon"]).astype(float)
    lat2 = out["DOLocationID"].map(z["centroid_lat"]).astype(float)
    straight = _haversine_mi(lon1, lat1, lon2, lat2)
    same_zone = out["PULocationID"] == out["DOLocationID"]
    # Under 0.25 mi between centroids the ratio explodes on rounding noise; skip.
    usable = (~same_zone) & (straight > 0.25)
    out["straight_line_mi"] = np.where(usable, straight.round(3), np.nan)
    out["detour_index"] = np.where(usable, (out["trip_distance"] / straight).round(3), np.nan)

    pu_b = out["PULocationID"].map(z["borough"])
    do_b = out["DOLocationID"].map(z["borough"])
    out["is_cross_borough"] = (pu_b != do_b).astype("int8")
    out["is_airport_trip"] = (out["PULocationID"].isin(AIRPORT_ZONES)
                              | out["DOLocationID"].isin(AIRPORT_ZONES)).astype("int8")

    out["distance_band_id"] = band(out["trip_distance"], DISTANCE_BANDS)
    out["fare_band_id"] = band(out["fare_amount"], FARE_BANDS)

    print(f"[features] median speed {out['avg_speed_mph'].median():.1f} mph · "
          f"median $/mi {out['fare_per_mile'].median():.2f} · "
          f"median card tip {np.nanmedian(out['tip_pct']):.1f}% · "
          f"median detour {np.nanmedian(out['detour_index']):.2f}")
    return out
