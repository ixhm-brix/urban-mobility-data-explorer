"""Helpers shared by every blueprint."""
from __future__ import annotations

from flask import jsonify, request

from backend.queries.filters import Filters


def filters() -> Filters:
    return Filters.from_args(request.args)


def ok(data, f: Filters | None = None, target: str = "agg", **meta):
    """Uniform envelope: {data, meta}. meta.ignored_filters tells the UI when a
    panel could not honour every active filter, so it can say so instead of lying."""
    body = {"data": data, "meta": dict(meta)}
    if f is not None:
        body["meta"]["ignored_filters"] = f.ignored_by(target)
    return jsonify(body)
