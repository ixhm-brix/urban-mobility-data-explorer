# API contract

Base URL: `http://127.0.0.1:5000`. All endpoints are `GET` and return JSON.

## Envelope

Every successful response has the same shape:

```json
{
  "data": { },
  "meta": { "ignored_filters": [] }
}
```

- `data` holds the payload: an object or an array, depending on the endpoint.
- `meta` holds context: paging, ranking details, and `ignored_filters`.
  `ignored_filters` lists any active filters this endpoint could not apply. For example, the route endpoints read the origin–destination roll-up, which has no date column. The dashboard shows a note when this list is not empty.

Errors look like this:

| Status | `error` | When |
|---|---|---|
| 400 | `invalid_filter` | A query parameter fails validation (bad date, out-of-range id, unknown sort key). |
| 404 | `not_found` | Unknown zone id or trip id. |
| 503 | `query_timeout` | A filter combination needed a scan longer than `QUERY_TIMEOUT_S` (default 8 s). |
| 503 | `database_missing` | The SQLite file has not been built yet. |

```json
{ "error": "invalid_filter", "message": "hour_from must be between 0 and 23" }
```

## Shared filters

Every analytical endpoint accepts the same optional query parameters. Combine them freely.

| Param | Type | Example | Meaning |
|---|---|---|---|
| `start` | `YYYY-MM-DD` | `2019-01-07` | Pickup date, inclusive |
| `end` | `YYYY-MM-DD` | `2019-01-13` | Pickup date, inclusive |
| `hour_from` | 0–23 | `22` | Pickup hour window start |
| `hour_to` | 0–23 | `4` | Pickup hour window end. If `hour_from` > `hour_to`, the window wraps past midnight. |
| `days` | list of 0–6 | `5,6` | Day of week (0 = Monday) |
| `borough` | id | `4` | Pickup borough (ids from `/api/meta`) |
| `zone` | 1–265 | `161` | Pickup zone (overrides `borough`) |
| `payment` | list of ids | `1,2` | Payment type |
| `dist` | list of ids | `1,2` | Distance band: 1 = under 1 mi, 2 = 1–2, 3 = 2–5, 4 = 5–10, 5 = 10–20, 6 = 20+ |
| `fare` | list of ids | `4,5` | Fare band: 1 = under $10, 2 = $10–20, 3 = $20–40, 4 = $40–70, 5 = $70+ |

Lists are comma-separated.

## Metric fields

Every aggregate row carries these fields. All are ratio-of-sums, so a zone with 30,000 trips weighs more than a zone with 3.

| Field | Definition |
|---|---|
| `trips` | Trip count |
| `revenue` | Σ total_amount (USD) |
| `avg_fare` | Σ fare ÷ trips |
| `avg_distance` | Σ miles ÷ trips |
| `avg_duration` | Σ minutes ÷ trips |
| `avg_speed` | Σ miles ÷ Σ hours (network speed, mph) |
| `fare_per_mile` | Σ fare ÷ Σ miles |
| `tip_pct` | Mean card tip as a % of fare (card trips only; cash tips are not recorded) |
| `airport_share` | % of trips touching JFK, LaGuardia or Newark |
| `cross_borough_share` | % of trips ending in a different borough |
| `card_share` | % of trips paid by card |

## Endpoints

### Reference

| Endpoint | Returns |
|---|---|
| `GET /api/health` | `{status, trips}` |
| `GET /api/meta` | Date range, boroughs, zones, payment types, distance/fare/time bands, and the last load run. Used to build the filter controls. |
| `GET /api/quality` | `{run, rules[]}`: the cleaning log. Each rule has `rule_code`, `action` (`excluded`, `flagged` or `repaired`), `description` and `record_count`. |

### Overview and time

| Endpoint | Returns |
|---|---|
| `GET /api/summary` | `{current, baseline}`. KPIs for the filtered set and for the whole month, so the client can show deltas. `current.days` is the number of distinct dates. |
| `GET /api/timeseries/daily` | `[{date, dow, …metrics}]`, one row per day |
| `GET /api/timeseries/hourly` | `[{hour, time_band, days, …metrics}]`. Divide `trips` by `days` for an average hour. |
| `GET /api/heatmap` | `[{dow, hour, days, trips_per_day, …metrics}]`, a 7 × 24 grid normalised by the number of matching dates |
| `GET /api/insights` | Three insight cards: `[{id, title, headline, detail, value, value_label, series[], unit}]` |

### Space

| Endpoint | Returns |
|---|---|
| `GET /api/zones/geojson` | A FeatureCollection of 263 zone polygons in WGS84. `feature.id` = LocationID. Cached by the server. |
| `GET /api/zones/metrics` | `[{location_id, zone, borough, …metrics}]`, one row per pickup zone |
| `GET /api/zones/rank?metric=&order=&k=&min_trips=` | Top-K zones. `metric` is any metric field; `order` is `desc` (default) or `asc`; `k` defaults to 10; `min_trips` defaults to 100. Ranked with `algorithms/top_k_heap.py`. `meta.candidates` = zones considered. |
| `GET /api/zones/<id>` | `{zone, metrics, hourly[], top_destinations[], top_origins[]}` |

### Routes

| Endpoint | Returns |
|---|---|
| `GET /api/routes/top?by=&order=&k=&min_trips=&same_zone=` | Top-K origin→destination pairs. `by` is one of `trips`, `avg_fare`, `avg_distance`, `avg_duration`, `avg_speed` or `detour_index`. `min_trips` defaults to 50 for averages. `same_zone=1` keeps trips that start and end in the same zone. Applies only the hour, day and area filters (see `meta.ignored_filters`). |
| `GET /api/flows/boroughs` | Borough × borough matrix: `[{origin, destination, trips, avg_fare, …}]` |

### Economics

| Endpoint | Returns |
|---|---|
| `GET /api/breakdown/distance` | `[{band_id, label, …metrics}]`, one row per distance band |
| `GET /api/breakdown/payment` | `[{id, label, …metrics}]`, one row per payment type |

### Trips

| Endpoint | Returns |
|---|---|
| `GET /api/trips?sort=&order=&page=&page_size=` | One page of trips. `sort` is one of `pickup`, `distance`, `fare`, `duration` or `speed` (all indexed); `order` is `desc` or `asc`; `page_size` is at most 100. `meta` = `{page, page_size, total, pages, sort, order}`. |
| `GET /api/trips/<id>` | `{trip, route_peers}`. Every column, with labels joined in, plus the average for the same route, hour and day type, for comparison. |

## Example

```
GET /api/routes/top?by=detour_index&hour_from=7&hour_to=9&k=1
```

```json
{
  "data": [
    { "pu_id": 209, "do_id": 87, "trips": 61, "avg_fare": 6.77, "avg_distance": 0.96,
      "avg_duration": 7.5, "avg_speed": 7.68, "detour_index": 3.773,
      "pu_zone": "Seaport", "pu_borough": "Manhattan",
      "do_zone": "Financial District North", "do_borough": "Manhattan" }
  ],
  "meta": { "by": "detour_index", "candidates": 2252, "algorithm": "top_k_heap",
            "partial_days": false, "ignored_filters": [] }
}
```

## Mock data

`frontend/mock/sample_responses.json` holds one recorded, unfiltered response per endpoint. Open the dashboard with `?mock=1` to use it, or let `api.js` fall back to it automatically when the API is unreachable. To regenerate it, start the API and run `python frontend/mock/record_mock.py`.
