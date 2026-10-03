"""
Database access: one read-only SQLite connection per thread, a small result
cache, and a watchdog that stops runaway queries instead of hanging the API.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUERY_DIR = Path(__file__).resolve().parent / "queries"

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

DB_PATH = Path(os.getenv("DB_PATH", "database/urban_mobility.db"))
if not DB_PATH.is_absolute():
    DB_PATH = ROOT / DB_PATH
QUERY_TIMEOUT_S = float(os.getenv("QUERY_TIMEOUT_S", "8"))
CACHE_SIZE = int(os.getenv("CACHE_SIZE", "512"))

_local = threading.local()


class QueryTimeout(Exception):
    pass


def get_connection() -> sqlite3.Connection:
    con = getattr(_local, "con", None)
    if con is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(
                f"Database not found at {DB_PATH}. Run: python pipeline/run_pipeline.py "
                f"&& python database/load_data.py")
        # mode=ro: the API can never modify the data it serves.
        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA cache_size = -131072")   # 128 MB page cache per thread
        con.execute("PRAGMA mmap_size = 1073741824")  # let the OS page the file in
        _local.con = con
    return con


def load_sql(name: str) -> str:
    """Read backend/queries/<name>.sql (cached)."""
    cache = _sql_files
    if name not in cache:
        cache[name] = (QUERY_DIR / f"{name}.sql").read_text()
    return cache[name]


_sql_files: dict[str, str] = {}


class _LRU:
    def __init__(self, size: int):
        self.size, self.data, self.lock = size, OrderedDict(), threading.Lock()

    def get(self, key):
        with self.lock:
            if key in self.data:
                self.data.move_to_end(key)
                return self.data[key]
        return None

    def put(self, key, value):
        with self.lock:
            self.data[key] = value
            self.data.move_to_end(key)
            while len(self.data) > self.size:
                self.data.popitem(last=False)


_cache = _LRU(CACHE_SIZE)


def query(sql: str, params: list | tuple = (), cache: bool = True) -> list[dict]:
    """Run a SELECT and return rows as dicts. The data is static between loads,
    so identical (sql, params) pairs are served from memory."""
    key = (sql, json.dumps(list(params), default=str))
    if cache:
        hit = _cache.get(key)
        if hit is not None:
            return hit
    con = get_connection()
    deadline = time.monotonic() + QUERY_TIMEOUT_S
    # Called every 100k VM steps; returning non-zero aborts the statement.
    con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 100_000)
    try:
        rows = [dict(r) for r in con.execute(sql, params).fetchall()]
    except sqlite3.OperationalError as exc:
        if "interrupted" in str(exc):
            raise QueryTimeout("This combination of filters needs a scan longer than "
                               f"{QUERY_TIMEOUT_S:g}s. Narrow the date or zone filter.") from exc
        raise
    finally:
        con.set_progress_handler(None, 0)
    if cache:
        _cache.put(key, rows)
    return rows


def query_one(sql: str, params: list | tuple = (), cache: bool = True) -> dict | None:
    rows = query(sql, params, cache)
    return rows[0] if rows else None
