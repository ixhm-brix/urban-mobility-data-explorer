"""
Turns dashboard query-string filters into a parameterised SQL WHERE clause.

Every value goes through validation and is bound as a parameter; only column
names chosen by this module are interpolated, so filters cannot inject SQL.

Supported filters (all optional, combinable):

    start, end        YYYY-MM-DD, inclusive            pickup date range
    hour_from, hour_to 0–23; from > to wraps midnight  pickup hour window
    days              comma list of 0–6 (0 = Monday)   day of week
    borough           borough_id                       pickup borough
    zone              location_id                      pickup zone
    payment           comma list of payment_type_id
    dist              comma list of distance_band_id
    fare              comma list of fare_band_id

The same filter set compiles against three targets:
    "agg"   -> agg_zone_hour (fast path for charts)
    "trips" -> trips         (trip explorer)
    "od"    -> agg_od        (route ranking: supports a subset, see SUPPORTED)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SUPPORTED = {
    "agg": {"start", "end", "hours", "days", "borough", "zone", "payment", "dist", "fare"},
    "trips": {"start", "end", "hours", "days", "borough", "zone", "payment", "dist", "fare"},
    "od": {"hours", "days", "borough", "zone"},
}


class FilterError(ValueError):
    pass


@dataclass
class Filters:
    start: str | None = None
    end: str | None = None
    hour_from: int | None = None
    hour_to: int | None = None
    days: list[int] = field(default_factory=list)
    borough: int | None = None
    zone: int | None = None
    payment: list[int] = field(default_factory=list)
    dist: list[int] = field(default_factory=list)
    fare: list[int] = field(default_factory=list)

    # ------------------------------------------------------------- parsing
    @classmethod
    def from_args(cls, args) -> "Filters":
        f = cls()
        f.start = _date(args.get("start"), "start")
        f.end = _date(args.get("end"), "end")
        if f.start and f.end and f.start > f.end:
            raise FilterError("start must be on or before end")
        f.hour_from = _int(args.get("hour_from"), "hour_from", 0, 23)
        f.hour_to = _int(args.get("hour_to"), "hour_to", 0, 23)
        f.days = _int_list(args.get("days"), "days", 0, 6)
        f.borough = _int(args.get("borough"), "borough", 1, 50)
        f.zone = _int(args.get("zone"), "zone", 1, 265)
        f.payment = _int_list(args.get("payment"), "payment", 1, 6)
        f.dist = _int_list(args.get("dist"), "dist", 1, 6)
        f.fare = _int_list(args.get("fare"), "fare", 1, 5)
        return f

    def active(self) -> set[str]:
        on = set()
        if self.start: on.add("start")
        if self.end: on.add("end")
        if self.hour_from is not None or self.hour_to is not None: on.add("hours")
        if self.days and len(self.days) < 7: on.add("days")
        for name in ("borough", "zone"):
            if getattr(self, name) is not None: on.add(name)
        for name in ("payment", "dist", "fare"):
            if getattr(self, name): on.add(name)
        return on

    def ignored_by(self, target: str) -> list[str]:
        """Filters the user set that this target cannot honour (reported to the UI)."""
        return sorted(self.active() - SUPPORTED[target])

    # ------------------------------------------------------------ compiling
    def where(self, target: str = "agg", alias: str = "", scan_area: bool = False) -> tuple[str, list]:
        """scan_area=True writes the borough test as `+col IN (...)`, which tells SQLite
        not to drive the query from the zone index. Used by the trip explorer when the
        borough is large, so the ORDER BY index can be walked instead of sorting millions."""
        p = f"{alias}." if alias else ""
        clauses: list[str] = []
        params: list = []
        on = self.active()

        if target == "trips":
            # Range on the raw timestamp keeps the pickup_datetime index usable.
            if self.start:
                clauses.append(f"{p}pickup_datetime >= ?"); params.append(self.start)
            if self.end:
                nxt = (date.fromisoformat(self.end) + timedelta(days=1)).isoformat()
                clauses.append(f"{p}pickup_datetime < ?"); params.append(nxt)
        elif target == "agg":
            if self.start:
                clauses.append(f"{p}pickup_date >= ?"); params.append(self.start)
            if self.end:
                clauses.append(f"{p}pickup_date <= ?"); params.append(self.end)

        if "hours" in on:
            lo = 0 if self.hour_from is None else self.hour_from
            hi = 23 if self.hour_to is None else self.hour_to
            if lo <= hi:
                clauses.append(f"{p}pickup_hour BETWEEN ? AND ?")
            else:  # e.g. 22 -> 4 : late-night window crossing midnight
                clauses.append(f"({p}pickup_hour >= ? OR {p}pickup_hour <= ?)")
            params += [lo, hi]

        if "days" in on:
            if target == "od":
                # agg_od only knows weekday vs weekend; honour it when the selection is one of the two.
                kinds = {1 if d >= 5 else 0 for d in self.days}
                if len(kinds) == 1:
                    clauses.append(f"{p}is_weekend = ?"); params.append(kinds.pop())
            else:
                clauses.append(_in(f"{p}pickup_dow", self.days)); params += self.days

        if self.zone is not None:
            clauses.append(f"{p}pu_location_id = ?"); params.append(self.zone)
        elif self.borough is not None:
            plus = "+" if scan_area else ""
            clauses.append(f"{plus}{p}pu_location_id IN (SELECT location_id FROM zones WHERE borough_id = ?)")
            params.append(self.borough)

        if target != "od":
            for name, col in (("payment", "payment_type_id"), ("dist", "distance_band_id"),
                              ("fare", "fare_band_id")):
                values = getattr(self, name)
                if values:
                    clauses.append(_in(f"{p}{col}", values)); params += values

        return ("WHERE " + " AND ".join(clauses)) if clauses else "", params

    def od_is_partial(self) -> bool:
        """True when a day selection mixes weekdays and weekends in a way agg_od can't express."""
        if "days" not in self.active():
            return False
        return len({1 if d >= 5 else 0 for d in self.days}) > 1


# ------------------------------------------------------------------ helpers
def _in(col: str, values: list) -> str:
    return f"{col} IN ({', '.join('?' * len(values))})"


def _date(v, name):
    if v in (None, ""):
        return None
    if not DATE_RE.match(v):
        raise FilterError(f"{name} must be YYYY-MM-DD")
    try:
        date.fromisoformat(v)
    except ValueError as exc:
        raise FilterError(f"{name} is not a valid date") from exc
    return v


def _int(v, name, lo, hi):
    if v in (None, ""):
        return None
    try:
        n = int(v)
    except (TypeError, ValueError) as exc:
        raise FilterError(f"{name} must be an integer") from exc
    if not lo <= n <= hi:
        raise FilterError(f"{name} must be between {lo} and {hi}")
    return n


def _int_list(v, name, lo, hi):
    if v in (None, ""):
        return []
    out = []
    for part in str(v).split(","):
        n = _int(part.strip(), name, lo, hi)
        if n is not None and n not in out:
            out.append(n)
    return out
