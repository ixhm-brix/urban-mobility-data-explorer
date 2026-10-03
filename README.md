# Urban Mobility Data Explorer

How New York moved in January 2019. This project cleans **7.7 million NYC yellow-taxi trips**, stores them in a normalised SQLite database and serves an interactive dashboard for exploring urban mobility by time, place, route and price.

![Architecture](docs/architecture.png)

| | |
|---|---|
| **Pipeline** | Python · pandas · pyarrow. Loads the parquet trips, zone lookup and zone shapefile; applies 16 cleaning rules (every exclusion is logged) and engineers 4 features. |
| **Database** | SQLite star schema, 10 dimension tables, indexed `trips` fact table (7,583,231 rows), plus two roll-up tables for fast charts. |
| **Backend** | Flask JSON API: parameterised SQL, validated filters, result cache, query watchdog. |
| **Algorithm** | Hand-written binary min-heap for top-K ranking, O(n log k) (`algorithms/top_k_heap.py`). |
| **Frontend** | Plain HTML, CSS and JavaScript with Chart.js: a filter form, summary cards, charts, ranking tables, a sortable trip table and a trip-detail popup. |

Further documentation:
- [docs/report.pdf](docs/report.pdf): the technical report.
- [docs/api_contract.md](docs/api_contract.md): every API endpoint.

---

## 1. Setup

You need Python 3.10 or newer, about 4 GB of free disk and about 6 GB of RAM for the pipeline step.

```bash
git clone <repo-url> urban-mobility-data-explorer
cd urban-mobility-data-explorer
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # optional; the defaults work
```

## 2. Get the raw data

The raw files are too large for git. Put them in `data/raw/`:

```
data/raw/
├── yellow_tripdata_2019-01.parquet   # trips (fact table)
├── taxi_zone_lookup.csv              # zone → borough / service zone
└── taxi_zones/                       # unzipped shapefile (.shp .shx .dbf .prj …)
```

```bash
curl -L -o data/raw/yellow_tripdata_2019-01.parquet \
  https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2019-01.parquet
curl -L -o data/raw/taxi_zone_lookup.csv \
  https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv
curl -L -o /tmp/taxi_zones.zip https://d37ci6vzurychx.cloudfront.net/misc/taxi_zones.zip
unzip /tmp/taxi_zones.zip -d data/raw/taxi_zones
```

The loader also accepts a `yellow_tripdata*.csv` in place of the parquet file.

## 3. Build the data and the database

```bash
python pipeline/run_pipeline.py        # ~1 min  → data/processed/ + pipeline/logs/
python database/load_data.py           # ~4 min  → database/urban_mobility.db (2.4 GB)
python database/load_data.py --dump    # same, plus SQL dumps in database/dump/ (~7 min)
```

For a quick development run on a subset, use `python pipeline/run_pipeline.py --limit 200000`.

## 4. Run the app

```bash
python backend/app.py
```

Then open **http://127.0.0.1:5000**. The Flask server serves both the API and the dashboard.

To work on the frontend without the database, open `http://127.0.0.1:5000/?mock=1`, or any static server pointed at `frontend/` with `?mock=1`. In mock mode the dashboard reads recorded responses from `frontend/mock/sample_responses.json`.

---

## Project structure

```
urban-mobility-data-explorer/
├── data/                  raw/ and processed/ (git-ignored)
├── pipeline/
│   ├── load.py            read parquet + lookup; reproject shapefile → GeoJSON; fix zone-ID defects
│   ├── clean.py           16 exclusion rules, repairs, duplicate detection, suspicious-record flags
│   ├── features.py        speed, $/mile, card tip %, detour index (+ time keys, bands)
│   ├── run_pipeline.py    entry point; normalises names, types and timestamps
│   └── logs/              excluded_records.csv · suspicious_records.csv · cleaning_summary.json
├── database/
│   ├── schema.sql         tables, keys, CHECK constraints, indexes (each one justified)
│   ├── load_data.py       bulk insert → indexes → roll-ups → integrity checks → ANALYZE
│   └── dump/              urban_mobility_sample.sql (schema, all dimensions, 5,000 trips)
├── backend/
│   ├── app.py             Flask entry point, error envelope, gzip, static hosting
│   ├── db.py              read-only connections, LRU cache, query watchdog
│   ├── routes/            meta · analytics · zones · flows · trips · quality · insights
│   └── queries/           the SQL behind every filter (*.sql) + filters.py (WHERE builder)
├── algorithms/
│   ├── top_k_heap.py      manual min-heap + merge sort; run it to self-test
│   └── insights.py        the three insight queries
├── frontend/
│   ├── index.html
│   ├── css/styles.css
│   ├── js/                api.js (all fetches) · charts.js (Chart.js) · filters.js · app.js
│   └── mock/              sample_responses.json + record_mock.py
└── docs/                  architecture.png · api_contract.md · report.pdf (+ HTML sources)
```

## Cleaning results

| | Records |
|---|---|
| Raw | 7,696,617 |
| Excluded (logged with every rule broken) | 113,386 (1.47%) |
| **Loaded** | **7,583,231** |

The largest exclusion rules are: duration under 1 minute (67,801), zero distance (55,089), duration over 4 hours (20,766), fare below the $2.50 flag drop (10,866), negative components (7,134), speed over 65 mph (6,584) and drop-off before pickup (6,557).

The full list, the repairs and the "suspicious but kept" flags are in `pipeline/logs/cleaning_summary.json`, in the dashboard's **Data quality** section, and in report §2.

## The dashboard

A single page, top to bottom:

- **Filters:** start and end date, hour window (wraps past midnight, e.g. 10pm → 4am), weekdays or weekends, pickup borough, pickup zone, distance band, fare band and payment type. Press **Apply** to update every section, or **Reset** to clear.
- **Summary:** trips, revenue, average fare, distance, speed and card tip for the current filters.
- **Key insights:** three findings that recalculate under the filters.
- **Trends:** trips per day, average trips per hour, average speed by hour, and fare per mile by trip distance.
- **Locations:** top 10 pickup zones and top 10 routes, each with a dropdown to rank by trips, fare, speed, tip % or detour. The ranking uses the custom heap algorithm.
- **Trips:** a paginated table of individual trips. Click a column header to sort by pickup time, distance, duration, speed or fare; click a row to open its details, including a comparison with the same route at the same hour.
- **Data cleaning log:** every rule applied to the raw data, with how many records it excluded, flagged or repaired.

## Submission notes

- The database file and the full dump (`database/dump/urban_mobility_full.sql.gz`, ~290 MB) exceed GitHub's limits and are git-ignored. Share the full dump separately (for example a Drive link or a GitHub Release), or rebuild it with the commands above. The committed `urban_mobility_sample.sql` restores the schema, all dimensions and 5,000 trips: `sqlite3 sample.db < database/dump/urban_mobility_sample.sql`.
- Restore the full dump with: `gunzip -c database/dump/urban_mobility_full.sql.gz | sqlite3 urban_mobility.db`.
