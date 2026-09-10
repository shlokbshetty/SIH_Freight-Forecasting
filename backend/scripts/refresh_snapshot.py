#!/usr/bin/env python3
"""Rebuild data/snapshot.json from live sources.

Run this on a machine with network access. It pulls every adapter, writes the
result into the SQLite cache, then exports the cache to the committed snapshot
so the next cold, offline boot starts from real market data.

    python scripts/refresh_snapshot.py                # all sources
    python scripts/refresh_snapshot.py --days 1095    # how much history to keep
    python scripts/refresh_snapshot.py --allow-stale  # write even if a source failed

By default the export refuses to overwrite a good snapshot when any source came
back stale, so a rate-limited afternoon cannot quietly degrade the committed
offline baseline. Pass --allow-stale to override that.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import config  # noqa: E402
from data import cache, ingest  # noqa: E402

log = logging.getLogger("refresh_snapshot")


def export(conn, out: Path, days: int, provenance: str) -> dict:
    """Write the cache out in the columnar snapshot format."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = cache.read_observations(conn, since=cutoff)
    if not rows:
        raise SystemExit("cache is empty; nothing to export")

    by_metric: dict[str, dict[str, tuple[float, str]]] = {}
    for r in rows:
        by_metric.setdefault(r["metric"], {})[r["timestamp"][:10]] = (r["value"], r["source"])

    series: dict[str, dict] = {}
    for metric, points in sorted(by_metric.items()):
        stamps = sorted(points)
        start = date.fromisoformat(stamps[0])
        end = date.fromisoformat(stamps[-1])
        span = (end - start).days + 1
        values: list[float | None] = [None] * span
        source = points[stamps[-1]][1]
        for stamp in stamps:
            values[(date.fromisoformat(stamp) - start).days] = round(points[stamp][0], 4)
        series[metric] = {
            "adapter": cache.adapter_for_metric(metric),
            "source": source,
            "start": start.isoformat(),
            "freq": "D",
            "values": values,
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).date().isoformat(),
        "provenance": provenance,
        "note": "Exported from the live ingestion cache by scripts/refresh_snapshot.py.",
        "schema": "columnar-v1",
        "days": days,
        "series": series,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=1095, help="calendar days of history to keep")
    ap.add_argument("--out", type=Path, default=config.SNAPSHOT_FILE)
    ap.add_argument("--allow-stale", action="store_true")
    ap.add_argument("--skip-fetch", action="store_true", help="export whatever is already cached")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")

    conn = cache.connect(config.CACHE_DB)
    ingest.bootstrap(conn)

    stale: list[str] = []
    if not args.skip_fetch:
        for outcome in ingest.refresh_all(conn):
            status = "STALE" if outcome.is_stale else "ok"
            print(f"  {outcome.adapter:<12} {outcome.rows:>7,} rows  {status}")
            if outcome.is_stale:
                stale.append(outcome.adapter)

    if stale and not args.allow_stale:
        print(f"\nrefusing to export: {', '.join(stale)} came back stale.")
        print("Fix the source, or pass --allow-stale to write anyway.")
        return 1

    provenance = "live" if not stale else "live-partial"
    payload = export(conn, args.out, args.days, provenance)

    points = sum(sum(1 for v in s["values"] if v is not None) for s in payload["series"].values())
    print(f"\nwrote {args.out}")
    print(f"  provenance   {provenance}")
    print(f"  series       {len(payload['series'])}")
    print(f"  observations {points:,}")
    print(f"  size         {args.out.stat().st_size / 1024:,.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
