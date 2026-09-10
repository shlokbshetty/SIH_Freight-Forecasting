"""Runtime configuration.

Everything tunable is read from the environment so nothing sensitive is
committed. No key is required to run the app: every source used here is either
free and unauthenticated, or degrades to the committed snapshot.
"""

from __future__ import annotations

import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_ROOT / "data"
MODEL_DIR = BACKEND_ROOT / "models"

REFERENCE_DIR = DATA_DIR / "reference"
PORTS_DIR = DATA_DIR / "ports"

CACHE_DB = Path(os.getenv("FREIGHTIQ_CACHE_DB", DATA_DIR / "cache.db"))
SNAPSHOT_FILE = Path(os.getenv("FREIGHTIQ_SNAPSHOT", DATA_DIR / "snapshot.json"))
METRICS_FILE = Path(os.getenv("FREIGHTIQ_METRICS", MODEL_DIR / "metrics.json"))

# Committed reference data. Each backs an adapter that has no free live feed.
BUNKER_CSV = Path(os.getenv("FREIGHTIQ_BUNKER_CSV", REFERENCE_DIR / "bunker_vlsfo.csv"))
CONGESTION_FILE = Path(os.getenv("FREIGHTIQ_CONGESTION", REFERENCE_DIR / "congestion.json"))
CORRIDORS_FILE = Path(os.getenv("FREIGHTIQ_CORRIDORS", REFERENCE_DIR / "corridors.json"))

# Static AIS dump. Large, so it is downloaded rather than committed; the adapter
# reports it missing and the rest of the system carries on without it.
AIS_FILE = Path(os.getenv("FREIGHTIQ_AIS_FILE", REFERENCE_DIR / "ais_positions.csv"))

# Berth-level port data.
BERTHS_CSV = Path(os.getenv("FREIGHTIQ_BERTHS_CSV", PORTS_DIR / "berths.csv"))
LIGHTERAGE_CSV = Path(os.getenv("FREIGHTIQ_LIGHTERAGE_CSV", PORTS_DIR / "lighterage_nodes.csv"))

# ── Ingestion behaviour ───────────────────────────────────────────────────────

def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


#: Run the hourly APScheduler job. Turn off for tests and for CI.
SCHEDULER_ENABLED = _flag("FREIGHTIQ_SCHEDULER", True)

#: Minutes between scheduled refreshes.
REFRESH_INTERVAL_MINUTES = _int("FREIGHTIQ_REFRESH_MINUTES", 60)

#: Refresh once at startup. Off by default so a cold boot is instant and
#: offline-safe; the scheduler picks it up on the first tick.
REFRESH_ON_STARTUP = _flag("FREIGHTIQ_REFRESH_ON_STARTUP", False)

#: Block all outbound network calls. Every adapter falls back to cache.
#: Set this to prove the offline path works.
OFFLINE_MODE = _flag("FREIGHTIQ_OFFLINE", False)

#: A source older than this is reported stale by /api/data/status.
STALE_AFTER_MINUTES = _int("FREIGHTIQ_STALE_MINUTES", 180)

#: Seconds before an outbound HTTP call is abandoned.
HTTP_TIMEOUT_SECONDS = _int("FREIGHTIQ_HTTP_TIMEOUT", 15)

# ── CORS ──────────────────────────────────────────────────────────────────────

CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("FREIGHTIQ_CORS_ORIGINS", "http://localhost:5173,http://localhost:5174").split(",")
    if o.strip()
]
