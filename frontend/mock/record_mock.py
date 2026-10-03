"""
Record live API responses into sample_responses.json, so the dashboard can be
built and demoed without the 2.4 GB database (open index.html?mock=1).

    python backend/app.py &           # API must be running
    python frontend/mock/record_mock.py
"""
import json
import os
import urllib.request
from pathlib import Path

BASE = os.getenv("API_BASE", "http://127.0.0.1:5000")
ENDPOINTS = {
    "/api/meta": "/api/meta",
    "/api/health": "/api/health",
    "/api/quality": "/api/quality",
    "/api/summary": "/api/summary",
    "/api/insights": "/api/insights",
    "/api/timeseries/daily": "/api/timeseries/daily",
    "/api/timeseries/hourly": "/api/timeseries/hourly",
    "/api/zones/rank": "/api/zones/rank?metric=trips&order=desc&k=10",
    "/api/routes/top": "/api/routes/top?by=trips&order=desc&k=10",
    "/api/breakdown/distance": "/api/breakdown/distance",
    "/api/trips": "/api/trips?sort=pickup&order=desc&page=1&page_size=20",
    "/api/trips/:id": "/api/trips/12345",
}

out = {"_about": "Recorded responses from the live API (unfiltered). frontend/js/api.js serves "
                 "these when the page is opened with ?mock=1 or the API is unreachable. "
                 "Regenerate with: python frontend/mock/record_mock.py"}
for key, path in ENDPOINTS.items():
    with urllib.request.urlopen(BASE + path) as r:
        out[key] = json.load(r)
    print("recorded", key)
dest = Path(__file__).with_name("sample_responses.json")
dest.write_text(json.dumps(out, separators=(",", ":")))
print(f"wrote {dest} ({dest.stat().st_size / 1e6:.1f} MB)")
