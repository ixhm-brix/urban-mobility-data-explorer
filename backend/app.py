"""
Urban Mobility Data Explorer — Flask API + static dashboard.

    python backend/app.py            # http://127.0.0.1:5000
"""
from __future__ import annotations

import gzip
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flask import Flask, jsonify, request, send_from_directory  # noqa: E402
from werkzeug.exceptions import HTTPException                   # noqa: E402

from backend.db import QueryTimeout                             # noqa: E402
from backend.queries.filters import FilterError                 # noqa: E402
from backend.routes import analytics, flows, insights, meta, quality, trips, zones  # noqa: E402

FRONTEND = ROOT / "frontend"


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    app.json.sort_keys = False
    for module in (meta, analytics, zones, flows, trips, quality, insights):
        app.register_blueprint(module.bp)

    # ---------------------------------------------------------- errors
    @app.errorhandler(FilterError)
    def bad_filter(exc):
        return jsonify(error="invalid_filter", message=str(exc)), 400

    @app.errorhandler(QueryTimeout)
    def timeout(exc):
        return jsonify(error="query_timeout", message=str(exc)), 503

    @app.errorhandler(FileNotFoundError)
    def no_db(exc):
        return jsonify(error="database_missing", message=str(exc)), 503

    @app.errorhandler(HTTPException)
    def http_error(exc):
        if request.path.startswith("/api/"):
            return jsonify(error=exc.name.lower().replace(" ", "_"), message=exc.description), exc.code
        return exc

    # ------------------------------------------------- response shaping
    @app.after_request
    def finish(resp):
        resp.headers["Access-Control-Allow-Origin"] = os.getenv("CORS_ORIGIN", "*")
        # The zone GeoJSON is ~2 MB; JSON compresses ~8x.
        if (resp.mimetype == "application/json" and not resp.direct_passthrough
                and "gzip" in request.headers.get("Accept-Encoding", "")
                and resp.content_length and resp.content_length > 2048):
            resp.set_data(gzip.compress(resp.get_data(), compresslevel=5))
            resp.headers["Content-Encoding"] = "gzip"
            resp.headers["Vary"] = "Accept-Encoding"
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "public, max-age=300"
        else:
            # Dashboard files: always revalidate (cheap 304 via ETag) so edits show up at once.
            resp.headers["Cache-Control"] = "no-cache"
        return resp

    # ------------------------------------------------------ dashboard
    @app.get("/")
    def index():
        return send_from_directory(FRONTEND, "index.html")

    @app.get("/<path:path>")
    def static_files(path):
        return send_from_directory(FRONTEND, path)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")),
            debug=os.getenv("FLASK_DEBUG", "0") == "1", threaded=True)
