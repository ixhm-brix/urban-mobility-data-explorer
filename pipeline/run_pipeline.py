"""
Pipeline entry point:
    download -> load -> clean -> features -> normalise -> data/processed/

    python pipeline/run_pipeline.py                          # January 2019, all rows
    python pipeline/run_pipeline.py --months 2019-01 2019-02 # more data: several months
    python pipeline/run_pipeline.py --limit 100000           # quick test: first 100k rows per month

Missing raw files are downloaded from the TLC website automatically.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from download import download, DEFAULT_MONTHS  # noqa: E402
from load import load_all, ROOT          # noqa: E402
from clean import clean, set_period, write_summary   # noqa: E402
from features import add_features        # noqa: E402

PROCESSED = ROOT / "data" / "processed"

# Raw TLC name -> database name. One naming convention (snake_case) everywhere downstream.
RENAME = {
    "VendorID": "vendor_id",
    "tpep_pickup_datetime": "pickup_datetime",
    "tpep_dropoff_datetime": "dropoff_datetime",
    "RatecodeID": "rate_code_id",
    "store_and_fwd_flag": "store_and_fwd",
    "PULocationID": "pu_location_id",
    "DOLocationID": "do_location_id",
    "payment_type": "payment_type_id",
}
MONEY = ["fare_amount", "extra", "mta_tax", "tip_amount", "tolls_amount",
         "improvement_surcharge", "congestion_surcharge", "total_amount"]


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=RENAME)
    # Timestamps: one canonical text form (ISO-8601, local NYC time, second precision).
    # Sorts lexically == chronologically, so SQLite range filters stay index-friendly.
    for c in ("pickup_datetime", "dropoff_datetime"):
        df[c] = df[c].dt.floor("s").dt.strftime("%Y-%m-%d %H:%M:%S")
    for c in MONEY:
        df[c] = df[c].astype(float).round(2)
    df["trip_distance"] = df["trip_distance"].round(2)
    for c in ("vendor_id", "rate_code_id", "pu_location_id", "do_location_id", "payment_type_id"):
        df[c] = df[c].astype("int16")
    df["passenger_count"] = df["passenger_count"].astype("Int8")
    df["store_and_fwd"] = (df["store_and_fwd"] == "Y").astype("int8")
    return df.sort_values("pickup_datetime").reset_index(drop=True)


def main(months: list[str], limit: int | None = None) -> None:
    t0 = time.time()
    download(months)
    set_period(months)
    trips, zones, geo = load_all(months, limit)
    trips, summary = clean(trips)
    trips = add_features(trips, zones)
    trips = normalise(trips)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    trips.to_parquet(PROCESSED / "trips_clean.parquet", index=False)
    zones.to_csv(PROCESSED / "zones.csv", index=False)
    (PROCESSED / "taxi_zones.geojson").write_text(json.dumps(geo, separators=(",", ":")))
    summary["months"] = months
    summary["limit_per_month"] = limit
    summary["runtime_s"] = round(time.time() - t0, 1)
    path = write_summary(summary)

    print(f"[pipeline] wrote {len(trips):,} trips -> {PROCESSED}")
    print(f"[pipeline] summary -> {path.relative_to(ROOT)}  ({summary['runtime_s']} s)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", nargs="+", default=DEFAULT_MONTHS, help="months to load, e.g. 2019-01 2019-02")
    ap.add_argument("--limit", type=int, default=None, help="only read the first N rows of each month")
    args = ap.parse_args()
    main(args.months, args.limit)
