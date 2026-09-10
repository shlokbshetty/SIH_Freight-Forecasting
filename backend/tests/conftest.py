"""Shared fixtures.

Every test runs offline against a temporary cache seeded from the committed
snapshot. That is deliberate: the suite must pass on a machine with no network
and no credentials, which is the same guarantee the application makes.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Must be set before app.config is imported anywhere.
os.environ.setdefault("FREIGHTIQ_OFFLINE", "1")
os.environ.setdefault("FREIGHTIQ_SCHEDULER", "0")
os.environ.setdefault("FREIGHTIQ_REFRESH_ON_STARTUP", "0")


@pytest.fixture(scope="session")
def snapshot_path() -> Path:
    from app import config
    return config.SNAPSHOT_FILE


@pytest.fixture
def cache_db(tmp_path: Path) -> Path:
    return tmp_path / "cache.db"


@pytest.fixture
def conn(cache_db: Path):
    """A cache seeded from the committed snapshot, and nothing else."""
    from data import cache, ingest

    connection = cache.connect(cache_db)
    ingest.bootstrap(connection)
    yield connection
    connection.close()
