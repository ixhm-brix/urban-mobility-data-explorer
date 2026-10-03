"""
Stage 1 — Load.

Reads the three raw TLC components and integrates them:
  * yellow_tripdata  (.parquet, or .csv as a fallback)    -> fact table
  * taxi_zone_lookup.csv                                  -> zone dimension
  * taxi_zones shapefile (NY State Plane, US feet)        -> GeoJSON in WGS84

The shapefile is reprojected to longitude/latitude so a browser can draw it,
and each zone gets a centroid + area so the database can answer spatial
questions ("how far did the median trip from this zone travel?") without GIS.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import shapefile  # pyshp
from pyproj import CRS, Transformer

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

# Columns we keep from the fact table, with the dtype we want them in.
TRIP_COLUMNS = {
    "VendorID": "Int64",
    "tpep_pickup_datetime": "datetime64[us]",
    "tpep_dropoff_datetime": "datetime64[us]",
    "passenger_count": "Float64",
    "trip_distance": "float64",
    "RatecodeID": "Float64",
    "store_and_fwd_flag": "string",
    "PULocationID": "Int64",
    "DOLocationID": "Int64",
    "payment_type": "Int64",
    "fare_amount": "float64",
    "extra": "float64",
    "mta_tax": "float64",
    "tip_amount": "float64",
    "tolls_amount": "float64",
    "improvement_surcharge": "float64",
    "total_amount": "float64",
    "congestion_surcharge": "float64",
}


def find_trip_file() -> Path:
    """Prefer parquet (the official format); accept CSV so the course copy works too."""
    for pattern in ("yellow_tripdata*.parquet", "yellow_tripdata*.csv"):
        hits = sorted(RAW.glob(pattern))
        if hits:
            return hits[0]
    raise FileNotFoundError(f"No yellow_tripdata .parquet or .csv found in {RAW}")


def load_trips(path: Path | None = None, limit: int | None = None) -> pd.DataFrame:
    path = path or find_trip_file()
    if path.suffix == ".parquet":
        cols = [c for c in TRIP_COLUMNS if c in pq.read_schema(path).names]
        df = pd.read_parquet(path, columns=cols)
    else:
        df = pd.read_csv(path, low_memory=False,
                         parse_dates=["tpep_pickup_datetime", "tpep_dropoff_datetime"])
    if limit:
        df = df.head(limit)
    # Columns that are absent in some months (e.g. congestion_surcharge pre-2019) are added empty.
    for col, dtype in TRIP_COLUMNS.items():
        if col not in df.columns:
            df[col] = pd.Series(pd.NA, index=df.index, dtype="Float64" if dtype == "float64" else dtype)
    df = df[list(TRIP_COLUMNS)]
    # Remember the original row position so every excluded record can be traced back to the source file.
    df.insert(0, "source_row", range(len(df)))
    print(f"[load] {len(df):,} raw trips from {path.name}")
    return df


def load_zone_lookup() -> pd.DataFrame:
    z = pd.read_csv(RAW / "taxi_zone_lookup.csv")
    z.columns = ["location_id", "borough", "zone", "service_zone"]
    for c in ("borough", "zone", "service_zone"):
        z[c] = z[c].fillna("Unknown").str.strip()
    # 264 "Unknown/N/A" and 265 "N/A/Outside of NYC" are kept: trips really do reference them.
    z.loc[z["borough"].isin(["N/A"]), "borough"] = "Outside NYC"
    z.loc[z["service_zone"].isin(["N/A"]), "service_zone"] = "Unknown"
    print(f"[load] {len(z)} zones in lookup")
    return z


def _ring_area_and_centroid(ring):
    """Shoelace area/centroid on projected (planar, feet) coordinates."""
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if a == 0:
        return 0.0, ring[0]
    return a, (cx / (6 * a), cy / (6 * a))


def load_zone_shapes(lookup: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """Return (GeoJSON FeatureCollection in WGS84, per-zone centroid/area table)."""
    shp_dir = RAW / "taxi_zones"
    shp_path = next(shp_dir.rglob("*.shp"))
    reader = shapefile.Reader(str(shp_path))
    src_crs = CRS.from_wkt(shp_path.with_suffix(".prj").read_text())
    to_wgs84 = Transformer.from_crs(src_crs, "EPSG:4326", always_xy=True)

    ids_by_name: dict[str, list[int]] = {}
    for loc, name in zip(lookup["location_id"], lookup["zone"]):
        ids_by_name.setdefault(name, []).append(int(loc))
    used: set[int] = set()
    parts_by_id: dict[int, list] = {}
    stats: dict[int, list] = {}

    for sr in reader.iterShapeRecords():
        rec = sr.record.as_dict()
        loc_id = int(rec["LocationID"])
        # Known defect in the TLC shapefile: some polygons reuse a LocationID
        # (Corona 56/57 are both labelled 56; the harbour islands 103-105 are all 103).
        # When an ID repeats, hand the polygon the next unused ID that shares its zone name.
        candidates = ids_by_name.get(rec["zone"], [loc_id])
        if loc_id in used or loc_id not in candidates:
            free = [c for c in candidates if c not in used]
            if free:
                loc_id = free[0]
        used.add(loc_id)

        shape = sr.shape
        bounds = list(shape.parts) + [len(shape.points)]
        for i in range(len(shape.parts)):
            ring = shape.points[bounds[i]:bounds[i + 1]]
            area, (cx, cy) = _ring_area_and_centroid(ring)
            s = stats.setdefault(loc_id, [0.0, 0.0, 0.0])
            s[0] += area; s[1] += cx * area; s[2] += cy * area
            lon, lat = to_wgs84.transform([p[0] for p in ring], [p[1] for p in ring])
            # 5 decimals ≈ 1 m: plenty for a city-scale map and ~40 % smaller payload.
            parts_by_id.setdefault(loc_id, []).append(
                [[round(x, 5), round(y, 5)] for x, y in zip(lon, lat)]
            )

    features, rows = [], []
    for loc_id, rings in sorted(parts_by_id.items()):
        area, sx, sy = stats[loc_id]
        cx, cy = (sx / area, sy / area) if area else (0, 0)
        clon, clat = to_wgs84.transform(cx, cy)
        # Shapefile rings: clockwise = outer, counter-clockwise = hole. We keep it
        # simple and emit each ring as its own polygon; holes are rare in this layer.
        geometry = {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}
        meta = lookup.loc[lookup["location_id"] == loc_id].iloc[0]
        features.append({
            "type": "Feature",
            "id": loc_id,
            "properties": {"location_id": loc_id, "zone": meta["zone"], "borough": meta["borough"]},
            "geometry": geometry,
        })
        rows.append({
            "location_id": loc_id,
            "centroid_lon": round(clon, 6),
            "centroid_lat": round(clat, 6),
            # US survey feet² -> km²
            "area_km2": round(abs(area) * (0.3048006096 ** 2) / 1e6, 4),
        })

    geo = {"type": "FeatureCollection", "features": features}
    print(f"[load] {len(features)} zone polygons reprojected to WGS84")
    return geo, pd.DataFrame(rows)


def haversine_km(lon1, lat1, lon2, lat2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def load_all(limit: int | None = None):
    trips = load_trips(limit=limit)
    lookup = load_zone_lookup()
    geo, geo_stats = load_zone_shapes(lookup)
    zones = lookup.merge(geo_stats, on="location_id", how="left")
    return trips, zones, geo


if __name__ == "__main__":
    t, z, g = load_all(limit=1000)
    print(t.head()); print(z.head())
    print(json.dumps(g["features"][0]["properties"]))
