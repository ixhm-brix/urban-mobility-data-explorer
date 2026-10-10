"""
Stage 0 — Download the raw TLC files into data/raw/.

    python pipeline/download.py                        # January 2019 (default)
    python pipeline/download.py --months 2019-01 2019-02

Files that are already present are not downloaded again, so you can also
drop your own copies into data/raw/ and this step will just use them.
"""
from __future__ import annotations

import argparse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

TLC = "https://d37ci6vzurychx.cloudfront.net"
TRIPS_URL = TLC + "/trip-data/yellow_tripdata_{month}.parquet"
LOOKUP_URL = TLC + "/misc/taxi_zone_lookup.csv"
ZONES_URL = TLC + "/misc/taxi_zones.zip"

DEFAULT_MONTHS = ["2019-01"]


def fetch(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"[download] already have {dest.name}")
        return
    print(f"[download] {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.rename(dest)
    print(f"[download] saved {dest.name} ({dest.stat().st_size / 1e6:.0f} MB)")


def download(months: list[str] = DEFAULT_MONTHS) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for month in months:
        fetch(TRIPS_URL.format(month=month), RAW / f"yellow_tripdata_{month}.parquet")
    fetch(LOOKUP_URL, RAW / "taxi_zone_lookup.csv")

    zones_dir = RAW / "taxi_zones"
    if not any(zones_dir.rglob("*.shp")):
        zip_path = RAW / "taxi_zones.zip"
        fetch(ZONES_URL, zip_path)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(zones_dir)
        print("[download] unzipped taxi_zones.zip")
    else:
        print("[download] already have taxi_zones shapefile")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", nargs="+", default=DEFAULT_MONTHS, help="e.g. 2019-01 2019-02")
    download(ap.parse_args().months)
