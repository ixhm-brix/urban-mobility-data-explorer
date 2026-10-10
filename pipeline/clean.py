"""
Stage 2 — Clean.

Every rule is declared once in RULES with a code, a human description and a
vectorised test. A trip that fails any EXCLUDE rule is dropped and written to
logs/excluded_records.csv together with *all* the rules it broke. Rules that
can be repaired (missing values, sentinel codes) are applied as FIXES and
counted, so the report can quote exact numbers for both.

Thresholds are deliberately conservative and justified inline: the aim is to
remove records that are physically impossible or administratively void
(refunds, test rows, broken meters), not to trim legitimate long tails.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

LOG_DIR = Path(__file__).resolve().parent / "logs"

# Study window: the months being loaded. Anything outside it is a clock error on
# the meter (Jan 2019 contains pickups dated 2001, 2008 and even 2088).
# run_pipeline.py sets this from the --months argument.
PERIOD = {"start": pd.Timestamp("2019-01-01"), "end": pd.Timestamp("2019-02-01")}


def set_period(months: list[str]) -> None:
    starts = [pd.Timestamp(m + "-01") for m in months]
    PERIOD["start"] = min(starts)
    PERIOD["end"] = max(starts) + pd.offsets.MonthBegin(1)

MIN_DURATION_MIN = 1.0      # under a minute: meter started/stopped by accident
MAX_DURATION_MIN = 240.0    # 4 h: longer means the meter was left running
MIN_DISTANCE_MI = 0.01      # 0.0 mi with a fare is a "no-trip" / cancelled ride
MAX_DISTANCE_MI = 100.0     # far past any NYC fare zone incl. Newark & Westchester
MAX_SPEED_MPH = 65.0        # above NYC's top highway limit sustained door-to-door
MIN_FARE = 2.50             # the 2019 metered flag-drop; less is a refund/void
MAX_FARE = 500.0            # above any negotiated fare TLC publishes
MAX_PASSENGERS = 6          # largest legal yellow-cab capacity (minivan)

VALID_VENDORS = {1, 2, 4}           # 4 appears in 2019 files (Curb/other TPEP provider)
VALID_RATECODES = {1, 2, 3, 4, 5, 6}
VALID_PAYMENTS = {1, 2, 3, 4, 5, 6}
VALID_LOCATIONS = set(range(1, 266))


@dataclass
class Rule:
    code: str
    description: str
    test: Callable[[pd.DataFrame], pd.Series]   # True = record violates the rule


def _duration_min(df):
    return (df["tpep_dropoff_datetime"] - df["tpep_pickup_datetime"]).dt.total_seconds() / 60


def _total_gap(d):
    parts = (d["fare_amount"] + d["extra"] + d["mta_tax"] + d["tip_amount"] + d["tolls_amount"]
             + d["improvement_surcharge"] + d["congestion_surcharge"].fillna(0))
    return d["total_amount"] - parts


RULES: list[Rule] = [
    Rule("TIME_OUT_OF_PERIOD", "Pickup timestamp outside the months being loaded",
         lambda d: ~d["tpep_pickup_datetime"].between(PERIOD["start"], PERIOD["end"], inclusive="left")),
    Rule("TIME_NON_POSITIVE", "Dropoff is at or before pickup",
         lambda d: _duration_min(d) <= 0),
    Rule("DURATION_TOO_SHORT", f"Trip shorter than {MIN_DURATION_MIN:g} minute",
         lambda d: (_duration_min(d) > 0) & (_duration_min(d) < MIN_DURATION_MIN)),
    Rule("DURATION_TOO_LONG", f"Trip longer than {MAX_DURATION_MIN:g} minutes",
         lambda d: _duration_min(d) > MAX_DURATION_MIN),
    Rule("DISTANCE_ZERO", "Trip distance is zero or negative",
         lambda d: d["trip_distance"] < MIN_DISTANCE_MI),
    Rule("DISTANCE_TOO_LONG", f"Trip distance above {MAX_DISTANCE_MI:g} miles",
         lambda d: d["trip_distance"] > MAX_DISTANCE_MI),
    Rule("SPEED_IMPOSSIBLE", f"Average speed above {MAX_SPEED_MPH:g} mph",
         lambda d: (_duration_min(d) > 0)
         & (d["trip_distance"] / (_duration_min(d) / 60) > MAX_SPEED_MPH)),
    Rule("FARE_BELOW_MINIMUM", f"Fare below the ${MIN_FARE:.2f} flag-drop (refunds, voids)",
         lambda d: d["fare_amount"] < MIN_FARE),
    Rule("FARE_TOO_HIGH", f"Fare above ${MAX_FARE:g}",
         lambda d: d["fare_amount"] > MAX_FARE),
    Rule("NEGATIVE_COMPONENT", "A fee, tip, toll or surcharge is negative",
         lambda d: (d[["extra", "mta_tax", "tip_amount", "tolls_amount",
                       "improvement_surcharge"]] < 0).any(axis=1)),
    # A ~$2.50 gap is common in Jan 2019: some meters already billed the congestion
    # surcharge while leaving its column blank. That is logged as suspicious, not removed;
    # only gaps a surcharge cannot explain (> $5) are excluded.
    Rule("TOTAL_MISMATCH", "Total differs from the sum of its components by more than $5",
         lambda d: _total_gap(d).abs() > 5.0),
    Rule("PASSENGERS_OVER_CAPACITY", f"More than {MAX_PASSENGERS} passengers",
         lambda d: d["passenger_count"].fillna(0) > MAX_PASSENGERS),
    Rule("INVALID_VENDOR", "VendorID not in the TLC data dictionary",
         lambda d: ~d["VendorID"].isin(VALID_VENDORS)),
    Rule("INVALID_RATECODE", "RatecodeID is 99 or otherwise undefined",
         lambda d: d["RatecodeID"].notna() & ~d["RatecodeID"].isin(VALID_RATECODES)),
    Rule("INVALID_LOCATION", "Pickup or dropoff LocationID outside 1-265",
         lambda d: ~d["PULocationID"].isin(VALID_LOCATIONS) | ~d["DOLocationID"].isin(VALID_LOCATIONS)),
]

# Columns that identify the same physical trip. Two rows that agree on all of
# them are the same ride submitted twice by the vendor.
DUPLICATE_KEY = ["VendorID", "tpep_pickup_datetime", "tpep_dropoff_datetime",
                 "PULocationID", "DOLocationID", "trip_distance", "fare_amount"]

LOG_COLUMNS = ["source_file", "source_row", "reasons", "VendorID", "tpep_pickup_datetime", "tpep_dropoff_datetime",
               "trip_distance", "PULocationID", "DOLocationID", "passenger_count",
               "payment_type", "fare_amount", "tip_amount", "total_amount"]


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    n_raw = len(df)
    summary: dict = {"raw_rows": n_raw, "exclusions": {}, "fixes": {}, "rules": {}}

    # ---- 1. Exclusion rules ------------------------------------------------
    flags = pd.DataFrame({r.code: r.test(df).fillna(False).astype(bool) for r in RULES}, index=df.index)

    # ---- 2. Duplicates (judged only among otherwise-valid rows) -------------
    valid_so_far = ~flags.any(axis=1)
    dup = pd.Series(False, index=df.index)
    dup.loc[valid_so_far] = df.loc[valid_so_far].duplicated(subset=DUPLICATE_KEY, keep="first")
    flags["DUPLICATE_TRIP"] = dup

    for r in RULES:
        summary["rules"][r.code] = r.description
    summary["rules"]["DUPLICATE_TRIP"] = "Same vendor, timestamps, zones, distance and fare as an earlier row"
    summary["exclusions"] = {c: int(flags[c].sum()) for c in flags.columns}

    excluded_mask = flags.any(axis=1)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if excluded_mask.any():
        bad = flags.loc[excluded_mask]
        # "RULE_A|RULE_B" — every rule the record broke, not just the first.
        reasons = _fast_reasons(bad)
        log = df.loc[excluded_mask].copy()
        log["reasons"] = reasons
        log[LOG_COLUMNS].to_csv(LOG_DIR / "excluded_records.csv", index=False)

    out = df.loc[~excluded_mask].copy()

    # ---- 3. Repairs on the records we keep ---------------------------------
    fixes = summary["fixes"]

    # Passenger count 0 is the driver skipping the keypad, not an empty cab: unknown.
    zero_pax = out["passenger_count"] == 0
    fixes["passenger_count_zero_to_null"] = int(zero_pax.sum())
    out.loc[zero_pax, "passenger_count"] = pd.NA
    fixes["passenger_count_missing"] = int(out["passenger_count"].isna().sum()) - fixes["passenger_count_zero_to_null"]

    # The ~28 k rows with no RatecodeID / store_and_fwd_flag also report payment_type 0.
    # The trip itself is valid; we record the missing codes as "unknown" explicitly.
    fixes["ratecode_missing_to_unknown"] = int(out["RatecodeID"].isna().sum())
    out["RatecodeID"] = out["RatecodeID"].fillna(99)          # 99 = Unknown in the dimension table
    fixes["payment_type_zero_to_unknown"] = int((out["payment_type"] == 0).sum())
    out.loc[out["payment_type"] == 0, "payment_type"] = 5     # 5 = Unknown in the TLC dictionary
    fixes["store_fwd_missing_to_N"] = int(out["store_and_fwd_flag"].isna().sum())
    out["store_and_fwd_flag"] = out["store_and_fwd_flag"].fillna("N").str.upper().str.strip()

    # The NYS congestion surcharge only started on 2019-02-01, so blanks in January are $0.
    fixes["congestion_surcharge_null_to_zero"] = int(out["congestion_surcharge"].isna().sum())
    out["congestion_surcharge"] = out["congestion_surcharge"].fillna(0.0)

    # ---- 4. Suspicious-but-kept ---------------------------------------------
    # Plausible enough to keep, odd enough that an analyst should know they exist.
    dur = _duration_min(out)
    speed = out["trip_distance"] / (dur / 60)
    suspicious = {
        "TIP_EXCEEDS_FARE": out["tip_amount"] > out["fare_amount"],
        "CRAWL_SPEED": (speed < 2) & (dur > 30),
        "TOTAL_UNEXPLAINED_FEE": _total_gap(out).abs().between(1.0, 5.0, inclusive="right"),
        "UNKNOWN_ZONE": out["PULocationID"].isin([264, 265]) | out["DOLocationID"].isin([264, 265]),
        "NEGOTIATED_SHORT": (out["RatecodeID"] == 5) & (out["trip_distance"] < 1) & (out["fare_amount"] > 50),
    }
    sus = pd.DataFrame(suspicious)
    summary["suspicious_kept"] = {k: int(v.sum()) for k, v in suspicious.items()}
    summary["rules"].update({
        "TIP_EXCEEDS_FARE": "Kept: tip larger than the fare (generous or mistyped)",
        "CRAWL_SPEED": "Kept: under 2 mph for over 30 minutes (gridlock or meter left on)",
        "TOTAL_UNEXPLAINED_FEE": "Kept: total is $1-5 above its components (unlisted surcharge)",
        "UNKNOWN_ZONE": "Kept: pickup or dropoff zone is 264 Unknown / 265 Outside NYC",
        "NEGOTIATED_SHORT": "Kept: negotiated fare over $50 for under a mile",
    })
    any_sus = sus.any(axis=1)
    slog = out.loc[any_sus].copy()
    slog["reasons"] = _fast_reasons(sus.loc[any_sus])
    slog[LOG_COLUMNS].to_csv(LOG_DIR / "suspicious_records.csv", index=False)

    summary["clean_rows"] = len(out)
    summary["excluded_rows"] = int(excluded_mask.sum())
    summary["excluded_pct"] = round(100 * excluded_mask.mean(), 3)
    print(f"[clean] kept {len(out):,} of {n_raw:,} trips "
          f"({summary['excluded_rows']:,} excluded, {summary['excluded_pct']}%)")
    return out, summary


def _fast_reasons(bad: pd.DataFrame) -> pd.Series:
    """Vectorised 'A|B|C' join — the row-wise apply is too slow on ~10^5 rows."""
    parts = [np.where(bad[c].values, c + "|", "") for c in bad.columns]
    joined = parts[0].astype(object)
    for p in parts[1:]:
        joined = joined + p
    return pd.Series(joined, index=bad.index).str.rstrip("|")


def write_summary(summary: dict) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / "cleaning_summary.json"
    path.write_text(json.dumps(summary, indent=2))
    return path
