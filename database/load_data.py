"""
Build the SQLite database from the pipeline output.

    python database/load_data.py              # (re)build database/urban_mobility.db
    python database/load_data.py --dump       # also write database/dump/*.sql(.gz)

Steps: create tables -> insert dimensions -> stream trips in batches ->
build indexes -> build the roll-up table -> record data-quality metadata ->
ANALYZE (so the planner knows the row counts) -> integrity checks.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import pyarrow.parquet as pq
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from features import DISTANCE_BANDS, FARE_BANDS  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
SCHEMA = Path(__file__).with_name("schema.sql")
DUMP_DIR = Path(__file__).with_name("dump")
SUMMARY = ROOT / "pipeline" / "logs" / "cleaning_summary.json"

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass
DB_PATH = Path(os.getenv("DB_PATH", ROOT / "database" / "urban_mobility.db"))
if not DB_PATH.is_absolute():
    DB_PATH = ROOT / DB_PATH

# --- Reference data from the TLC Yellow Trip Record data dictionary -----------
VENDORS = [(1, "Creative Mobile Technologies"), (2, "VeriFone (Curb)"), (4, "Other TPEP provider")]
RATE_CODES = [(1, "Standard rate"), (2, "JFK flat fare"), (3, "Newark"), (4, "Nassau or Westchester"),
              (5, "Negotiated fare"), (6, "Group ride"), (99, "Unknown")]
PAYMENT_TYPES = [(1, "Credit card"), (2, "Cash"), (3, "No charge"), (4, "Dispute"),
                 (5, "Unknown"), (6, "Voided trip")]
BANDS = [(range(0, 6), "Overnight"), (range(6, 10), "Morning peak"), (range(10, 16), "Midday"),
         (range(16, 20), "Evening peak"), (range(20, 24), "Night")]

TRIP_COLUMNS = [
    "vendor_id", "pickup_datetime", "dropoff_datetime", "pickup_date", "pickup_hour", "pickup_dow",
    "is_weekend", "passenger_count", "trip_distance", "rate_code_id", "store_and_fwd",
    "pu_location_id", "do_location_id", "payment_type_id", "fare_amount", "extra", "mta_tax",
    "tip_amount", "tolls_amount", "improvement_surcharge", "congestion_surcharge", "total_amount",
    "trip_duration_min", "avg_speed_mph", "fare_per_mile", "tip_pct", "straight_line_mi",
    "detour_index", "is_cross_borough", "is_airport_trip", "distance_band_id", "fare_band_id",
]


def split_schema() -> tuple[str, str]:
    sql = SCHEMA.read_text()
    tables, _, indexes = sql.partition("-- @indexes")
    return tables, indexes


def connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def insert_dimensions(con: sqlite3.Connection) -> None:
    zones = pd.read_csv(PROCESSED / "zones.csv")
    boroughs = sorted(zones["borough"].unique())
    services = sorted(zones["service_zone"].unique())
    con.executemany("INSERT INTO boroughs VALUES (?, ?)", list(enumerate(boroughs, 1)))
    con.executemany("INSERT INTO service_zones VALUES (?, ?)", list(enumerate(services, 1)))
    b_id = {n: i for i, n in enumerate(boroughs, 1)}
    s_id = {n: i for i, n in enumerate(services, 1)}

    def nz(v):
        return None if pd.isna(v) else float(v)

    con.executemany(
        "INSERT INTO zones VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(int(r.location_id), r.zone, b_id[r.borough], s_id[r.service_zone],
          nz(r.centroid_lon), nz(r.centroid_lat), nz(r.area_km2)) for r in zones.itertuples()],
    )
    geo = json.loads((PROCESSED / "taxi_zones.geojson").read_text())
    con.executemany(
        "INSERT INTO zone_geometry VALUES (?, ?)",
        [(f["id"], json.dumps(f["geometry"], separators=(",", ":"))) for f in geo["features"]],
    )
    con.executemany("INSERT INTO vendors VALUES (?, ?)", VENDORS)
    con.executemany("INSERT INTO rate_codes VALUES (?, ?)", RATE_CODES)
    con.executemany("INSERT INTO payment_types VALUES (?, ?)", PAYMENT_TYPES)
    con.executemany("INSERT INTO distance_bands VALUES (?, ?, ?, ?)", DISTANCE_BANDS)
    con.executemany("INSERT INTO fare_bands VALUES (?, ?, ?, ?)", FARE_BANDS)
    con.executemany("INSERT INTO time_bands VALUES (?, ?, ?)",
                    [(h, name, order) for order, (hours, name) in enumerate(BANDS, 1) for h in hours])
    print(f"[db] dimensions: {len(zones)} zones, {len(boroughs)} boroughs, {len(geo['features'])} polygons")


def insert_trips(con: sqlite3.Connection, batch_size: int = 200_000) -> int:
    pf = pq.ParquetFile(PROCESSED / "trips_clean.parquet")
    placeholders = ", ".join("?" * len(TRIP_COLUMNS))
    sql = f"INSERT INTO trips ({', '.join(TRIP_COLUMNS)}) VALUES ({placeholders})"
    total = 0
    for batch in pf.iter_batches(batch_size=batch_size, columns=TRIP_COLUMNS):
        df = batch.to_pandas()
        # NaN -> NULL; numpy scalars -> Python scalars
        df = df.astype(object).where(df.notna(), None)
        con.executemany(sql, df.itertuples(index=False, name=None))
        total += len(df)
        print(f"\r[db] trips inserted: {total:,}/{pf.metadata.num_rows:,}", end="", flush=True)
    print()
    return total


AGG_SQL = """
INSERT INTO agg_zone_hour
SELECT pickup_date, pickup_hour, pickup_dow, pu_location_id, payment_type_id,
       distance_band_id, fare_band_id,
       COUNT(*), COALESCE(SUM(passenger_count), 0),
       SUM(trip_distance), SUM(trip_duration_min), SUM(fare_amount), SUM(tip_amount),
       SUM(total_amount), COALESCE(SUM(tip_pct), 0), COUNT(tip_pct),
       SUM(is_airport_trip), SUM(is_cross_borough), SUM(avg_speed_mph)
FROM trips
GROUP BY pickup_date, pickup_hour, pu_location_id, payment_type_id, distance_band_id, fare_band_id;

INSERT INTO agg_od
SELECT pu_location_id, do_location_id, pickup_hour, is_weekend,
       COUNT(*), SUM(trip_distance), SUM(trip_duration_min), SUM(fare_amount),
       COALESCE(SUM(detour_index), 0), COUNT(detour_index)
FROM trips
GROUP BY pu_location_id, do_location_id, pickup_hour, is_weekend;
"""


def record_quality(con: sqlite3.Connection) -> None:
    s = json.loads(SUMMARY.read_text())
    rows = [(code, "excluded", s["rules"][code], n) for code, n in s["exclusions"].items()]
    rows += [(code, "flagged", s["rules"][code], n) for code, n in s.get("suspicious_kept", {}).items()]
    rows += [(code.upper(), "repaired", code.replace("_", " "), n) for code, n in s["fixes"].items()]
    con.executemany("INSERT INTO data_quality_rules VALUES (?, ?, ?, ?)", rows)
    con.execute("INSERT INTO data_quality_run (raw_rows, clean_rows, excluded_rows) VALUES (?, ?, ?)",
                (s["raw_rows"], s["clean_rows"], s["excluded_rows"]))


def check_integrity(con: sqlite3.Connection) -> None:
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    if fk:
        sys.exit(f"[db] foreign key violations: {fk[:5]}")
    n_trips = con.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
    for table in ("agg_zone_hour", "agg_od"):
        n_agg = con.execute(f"SELECT SUM(trips) FROM {table}").fetchone()[0]
        assert n_trips == n_agg, f"{table} out of sync: {n_trips} vs {n_agg}"
    print(f"[db] integrity ok — {n_trips:,} trips, roll-up reconciles")


SAMPLE_TRIPS = 500
# Small lookup tables copied in full. zone_geometry is left out on purpose:
# it is ~2 MB of polygon coordinates and the full dump already contains it.
SAMPLE_TABLES = ("boroughs", "service_zones", "zones", "vendors", "rate_codes", "payment_types",
                 "distance_bands", "fare_bands", "time_bands", "data_quality_rules", "data_quality_run")


def write_dumps(db_path: Path, full: bool = True) -> None:
    """Standard SQLite dumps (same format as `sqlite3 db .dump`):
    a small sample you can open and read, and the whole database gzipped."""
    DUMP_DIR.mkdir(exist_ok=True)

    sample_db = DUMP_DIR / "sample.tmp.db"
    sample_db.unlink(missing_ok=True)
    con = sqlite3.connect(sample_db)
    con.executescript(split_schema()[0])
    con.execute("ATTACH DATABASE ? AS src", (str(db_path),))
    with con:
        for table in SAMPLE_TABLES:
            con.execute(f"INSERT INTO {table} SELECT * FROM src.{table}")
        con.execute(f"INSERT INTO trips SELECT * FROM src.trips ORDER BY trip_id LIMIT {SAMPLE_TRIPS}")
    con.execute("DETACH DATABASE src")
    sample = DUMP_DIR / "urban_mobility_sample.sql"
    sample.write_text("\n".join(con.iterdump()) + "\n")
    con.close()
    sample_db.unlink()
    print(f"[db] wrote {sample.relative_to(ROOT)} ({sample.stat().st_size / 1e3:.0f} KB)")

    if full:
        src = sqlite3.connect(db_path)
        out = DUMP_DIR / "urban_mobility_full.sql.gz"
        with gzip.open(out, "wt", compresslevel=6) as fh:
            for line in src.iterdump():
                fh.write(line + "\n")
        src.close()
        print(f"[db] wrote {out.relative_to(ROOT)} ({out.stat().st_size / 1e6:.0f} MB)")


def main(dump: bool) -> None:
    t0 = time.time()
    tmp = DB_PATH.with_suffix(".building")
    tmp.unlink(missing_ok=True)
    con = connect(tmp)
    # Bulk-load settings: safe because we build into a temp file and swap it in at the end.
    con.executescript("PRAGMA journal_mode = OFF; PRAGMA synchronous = OFF; PRAGMA cache_size = -512000;")
    tables_sql, index_sql = split_schema()
    con.executescript(tables_sql)
    with con:
        insert_dimensions(con)
    with con:
        insert_trips(con)
    print("[db] building indexes …")
    con.executescript(index_sql)
    print("[db] building roll-up …")
    with con:
        con.executescript(AGG_SQL)
        record_quality(con)
    con.execute("ANALYZE")
    check_integrity(con)
    con.close()
    tmp.replace(DB_PATH)
    if dump:
        write_dumps(DB_PATH)
    print(f"[db] ready: {DB_PATH} "
          f"({DB_PATH.stat().st_size / 1e9:.2f} GB, {time.time() - t0:.0f} s)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", action="store_true", help="rebuild the database, then write SQL dumps")
    ap.add_argument("--dump-only", action="store_true", help="only write the sample dump from the existing database")
    args = ap.parse_args()
    if args.dump_only:
        write_dumps(DB_PATH, full=False)
    else:
        main(args.dump)
