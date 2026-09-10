"""SQLite observation cache.

Deliberately stdlib-only. Ingestion hands it pandas frames, but the storage
layer itself speaks plain rows so that snapshot seeding, status reporting and
the offline boot path work even if the scientific stack is unavailable.

Two tables:

``observations``   one row per (metric, timestamp). ``fetched_at`` records when
                   we pulled it, which is distinct from ``timestamp``, the
                   moment the observation describes.
``source_status``  one row per adapter, carrying the outcome of its last run.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

log = logging.getLogger(__name__)

#: metric, timestamp (ISO-8601), value, source
Observation = tuple[str, str, float, str]

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    metric     TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    value      REAL NOT NULL,
    source     TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (metric, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_observations_metric ON observations (metric, timestamp);

CREATE TABLE IF NOT EXISTS source_status (
    source       TEXT PRIMARY KEY,
    last_fetched TEXT,
    last_success TEXT,
    is_stale     INTEGER NOT NULL DEFAULT 1,
    error        TEXT,
    row_count    INTEGER NOT NULL DEFAULT 0,
    is_proxy     INTEGER NOT NULL DEFAULT 0,
    source_label TEXT,
    notes        TEXT
);
"""

#: Columns added after the first release. SQLite has no IF NOT EXISTS for
#: ALTER TABLE ADD COLUMN, so an existing cache.db is migrated by inspection.
_LATE_COLUMNS = {
    "is_proxy": "INTEGER NOT NULL DEFAULT 0",
    "source_label": "TEXT",
    "notes": "TEXT",
}


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(source_status)")}
    for column, spec in _LATE_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE source_status ADD COLUMN {column} {spec}")
            log.info("migrated cache: added source_status.%s", column)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    with conn:
        _migrate(conn)
    return conn


# ── Writes ────────────────────────────────────────────────────────────────────

def write_observations(
    conn: sqlite3.Connection,
    rows: Iterable[Observation],
    fetched_at: str | None = None,
) -> int:
    """Upsert observations. Returns the number of rows written."""
    stamp = fetched_at or utcnow()
    payload = [
        (metric, str(timestamp), float(value), source, stamp)
        for metric, timestamp, value, source in rows
        if value is not None
    ]
    if not payload:
        return 0
    with conn:
        conn.executemany(
            "INSERT INTO observations (metric, timestamp, value, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(metric, timestamp) DO UPDATE SET "
            "value=excluded.value, source=excluded.source, fetched_at=excluded.fetched_at",
            payload,
        )
    return len(payload)


def write_status(
    conn: sqlite3.Connection,
    source: str,
    *,
    is_stale: bool,
    error: str | None = None,
    row_count: int = 0,
    succeeded: bool = True,
    is_proxy: bool = False,
    source_label: str | None = None,
    notes: list[str] | None = None,
) -> None:
    now = utcnow()
    note_blob = json.dumps(notes) if notes else None
    with conn:
        existing = conn.execute(
            "SELECT last_success FROM source_status WHERE source = ?", (source,)
        ).fetchone()
        last_success = now if succeeded else (existing["last_success"] if existing else None)
        conn.execute(
            "INSERT INTO source_status "
            "(source, last_fetched, last_success, is_stale, error, row_count, is_proxy, source_label, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(source) DO UPDATE SET "
            "last_fetched=excluded.last_fetched, last_success=excluded.last_success, "
            "is_stale=excluded.is_stale, error=excluded.error, row_count=excluded.row_count, "
            "is_proxy=excluded.is_proxy, source_label=excluded.source_label, notes=excluded.notes",
            (source, now, last_success, 1 if is_stale else 0, error, row_count,
             1 if is_proxy else 0, source_label, note_blob),
        )


# ── Reads ─────────────────────────────────────────────────────────────────────

def read_observations(
    conn: sqlite3.Connection,
    metrics: Sequence[str] | None = None,
    since: str | None = None,
) -> list[sqlite3.Row]:
    sql = "SELECT metric, timestamp, value, source, fetched_at FROM observations"
    clauses: list[str] = []
    params: list[object] = []
    if metrics:
        clauses.append(f"metric IN ({','.join('?' * len(metrics))})")
        params.extend(metrics)
    if since:
        clauses.append("timestamp >= ?")
        params.append(since)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY metric, timestamp"
    return conn.execute(sql, params).fetchall()


def latest_observation(conn: sqlite3.Connection, metric: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT metric, timestamp, value, source, fetched_at FROM observations "
        "WHERE metric = ? ORDER BY timestamp DESC LIMIT 1",
        (metric,),
    ).fetchone()


def known_metrics(conn: sqlite3.Connection) -> list[str]:
    return [r["metric"] for r in conn.execute("SELECT DISTINCT metric FROM observations ORDER BY metric")]


def count_for_source(conn: sqlite3.Connection, source_prefix: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM observations WHERE metric LIKE ?", (f"{source_prefix}%",)
    ).fetchone()
    return int(row["n"]) if row else 0


def purge_seeded(
    conn: sqlite3.Connection,
    metric: str,
    since: str,
    until: str,
    source_prefix: str = "synthetic:",
) -> int:
    """Drop seeded rows for one metric inside a window a live pull now covers.

    Without this, a snapshot dated to today shadows real market data that lags
    by a day or two, and ``latest_observation`` keeps returning the synthetic
    value after a successful refresh. The blend is invisible in the numbers and
    only shows in the per-row ``source``.

    Everything from ``since`` onward goes, not just the overlap. A seeded row
    dated after the live source's last observation is fiction claiming to be
    newer than the truth, and ``latest_observation`` would keep returning it
    after a successful refresh.

    Seeded history *before* ``since`` is left alone, because a live source with
    a short history (a ticker reset by a corporate action, say) would otherwise
    take three years of usable backfill down with it.
    """
    del until  # retained for call-site clarity; everything from `since` goes
    with conn:
        cur = conn.execute(
            "DELETE FROM observations WHERE metric = ? AND timestamp >= ? AND source LIKE ?",
            (metric, since, f"{source_prefix}%"),
        )
    return cur.rowcount or 0


def read_status(conn: sqlite3.Connection, stale_after_minutes: int) -> list[dict]:
    """Per-source freshness, as served by GET /api/data/status."""
    now = datetime.now(timezone.utc)
    out: list[dict] = []
    for row in conn.execute("SELECT * FROM source_status ORDER BY source"):
        last_fetched = parse_ts(row["last_fetched"])
        age_minutes = None
        if last_fetched:
            age_minutes = round((now - last_fetched).total_seconds() / 60, 1)
        # A source is stale if its adapter said so, or if nothing has landed
        # inside the freshness window regardless of what the adapter reported.
        is_stale = bool(row["is_stale"]) or age_minutes is None or age_minutes > stale_after_minutes
        keys = row.keys()
        raw_notes = row["notes"] if "notes" in keys else None
        try:
            notes = json.loads(raw_notes) if raw_notes else []
        except ValueError:
            notes = []
        out.append(
            {
                "source": row["source"],
                "last_fetched": row["last_fetched"],
                "last_success": row["last_success"],
                "is_stale": is_stale,
                "age_minutes": age_minutes,
                "row_count": row["row_count"],
                "error": row["error"],
                "is_proxy": bool(row["is_proxy"]) if "is_proxy" in keys else False,
                "source_label": (row["source_label"] if "source_label" in keys else None) or row["source"],
                "notes": notes,
            }
        )
    return out


def stale_sources(conn: sqlite3.Connection, stale_after_minutes: int) -> list[str]:
    return [s["source"] for s in read_status(conn, stale_after_minutes) if s["is_stale"]]


# ── Snapshot seeding ──────────────────────────────────────────────────────────
#
# The snapshot is stored column-wise rather than as one object per observation:
# a few hundred kilobytes instead of a few megabytes, and it diffs sanely.
#
#   {
#     "generated_at": "...", "provenance": "...",
#     "series": {
#       "<metric>": {"source": "...", "start": "YYYY-MM-DD", "freq": "D",
#                    "values": [1.0, 2.0, null, ...]}
#     }
#   }
#
# A null in ``values`` means no observation for that day, which is normal for
# any market series across weekends and holidays.

def _expand_series(metric: str, spec: dict) -> list[Observation]:
    from datetime import date, timedelta

    start = date.fromisoformat(spec["start"])
    step = timedelta(days=1 if spec.get("freq", "D") == "D" else 7)
    source = spec.get("source", "snapshot")
    rows: list[Observation] = []
    for i, value in enumerate(spec.get("values", [])):
        if value is None:
            continue
        rows.append((metric, (start + step * i).isoformat(), float(value), source))
    return rows


def adapter_for_metric(metric: str) -> str:
    """Adapter that owns a metric, taken from its namespace prefix."""
    return metric.split(".", 1)[0] if "." in metric else metric


def load_snapshot(path: Path) -> tuple[list[Observation], set[str]]:
    """Returns the observations and the set of adapters they belong to."""
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    rows: list[Observation] = []
    adapters: set[str] = set()
    for metric, spec in payload.get("series", {}).items():
        rows.extend(_expand_series(metric, spec))
        adapters.add(spec.get("adapter") or adapter_for_metric(metric))
    return rows, adapters


def seed_from_snapshot(conn: sqlite3.Connection, path: Path, force: bool = False) -> int:
    """Populate an empty cache from the committed snapshot.

    This is what makes a cold, network-free boot serve every screen. Existing
    rows are left alone unless ``force`` is set, so a seeded snapshot never
    overwrites a fresher live pull.
    """
    if not path.exists():
        log.warning("snapshot %s not found; starting with an empty cache", path)
        return 0

    if not force:
        existing = conn.execute("SELECT COUNT(*) AS n FROM observations").fetchone()
        if existing and existing["n"] > 0:
            log.info("cache already holds %s observations; skipping snapshot seed", existing["n"])
            return 0

    try:
        rows, adapters = load_snapshot(path)
    except (OSError, ValueError, KeyError) as exc:
        log.warning("could not read snapshot %s: %s", path, exc)
        return 0

    written = write_observations(conn, rows, fetched_at=utcnow())
    log.info("seeded %s observations from snapshot %s", written, path.name)

    # Mark every seeded adapter stale. The data is real in shape but old in
    # time, and the UI should say so rather than present it as live.
    for adapter in adapters:
        write_status(
            conn, adapter, is_stale=True, error="seeded from snapshot",
            row_count=sum(1 for r in rows if adapter_for_metric(r[0]) == adapter),
            succeeded=False,
        )
    return written
