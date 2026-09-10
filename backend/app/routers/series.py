"""GET /api/series - raw cached observations.

The typed endpoints answer specific commercial questions. This one exists so the
dashboard can read a metric it needs without the backend growing an endpoint per
chart: the Baltic ticker, the volatility gauge's inputs, corridor density, the
weather layer.

Reads only from the cache, like every other handler.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from app import config
from app.deps import get_conn, get_state, stale_sources, utcnow
from data import cache

router = APIRouter(prefix="/api", tags=["series"])

MAX_METRICS = 40
MAX_POINTS_PER_METRIC = 2_000


@router.get("/series")
def get_series(
    metrics: str | None = Query(None, description="Comma-separated metric names"),
    prefix: str | None = Query(None, description="Metric namespace, e.g. 'congestion'"),
    days: int = Query(365, ge=1, le=1825),
    latest_only: bool = Query(False, description="Return just the newest point per metric"),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    known = cache.known_metrics(conn)

    if metrics:
        wanted = [m.strip() for m in metrics.split(",") if m.strip()]
        missing = [m for m in wanted if m not in known]
    elif prefix:
        wanted = [m for m in known if m.startswith(prefix)]
        missing = []
    else:
        raise HTTPException(400, "pass either metrics= or prefix=")

    if not wanted:
        raise HTTPException(404, f"no metrics matched {metrics or prefix!r}")
    if len(wanted) > MAX_METRICS:
        raise HTTPException(400, f"{len(wanted)} metrics requested; cap is {MAX_METRICS}")

    since = (date.today() - timedelta(days=days)).isoformat()
    rows = cache.read_observations(conn, metrics=wanted, since=since)

    grouped: dict[str, dict] = {}
    for row in rows:
        entry = grouped.setdefault(row["metric"], {"source": row["source"], "points": []})
        entry["points"].append({"date": row["timestamp"], "value": row["value"]})
        entry["source"] = row["source"]

    for metric, entry in grouped.items():
        points = entry["points"]
        if latest_only:
            entry["points"] = points[-1:]
        elif len(points) > MAX_POINTS_PER_METRIC:
            # Thin evenly rather than truncating, so the shape survives.
            step = len(points) // MAX_POINTS_PER_METRIC + 1
            entry["points"] = points[::step] + points[-1:]
        entry["adapter"] = cache.adapter_for_metric(metric)

    proxy_adapters = {
        s["source"] for s in cache.read_status(conn, config.STALE_AFTER_MINUTES) if s["is_proxy"]
    }
    for entry in grouped.values():
        entry["is_proxy"] = entry["adapter"] in proxy_adapters

    return {
        "as_of": utcnow(),
        "sources_stale": stale_sources(conn),
        "requested": wanted,
        "missing": missing,
        "series": grouped,
    }


@router.get("/series/metrics")
def list_metrics(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    """Every metric the cache holds. Useful when wiring a new chart."""
    metrics = cache.known_metrics(conn)
    namespaces: dict[str, list[str]] = {}
    for metric in metrics:
        namespaces.setdefault(cache.adapter_for_metric(metric), []).append(metric)
    return {"as_of": utcnow(), "count": len(metrics), "namespaces": namespaces}
