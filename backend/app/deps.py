"""Shared request dependencies and process-wide state."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Request

from app import config

log = logging.getLogger(__name__)


@dataclass
class AppState:
    conn: sqlite3.Connection | None = None
    #: vessel class (lowercase) -> models.project.ProjectionBundle
    bundles: dict[str, object] = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    snapshot_provenance: str | None = None
    scheduler: object | None = None
    #: adapter name -> problems found at startup, from data.adapters.validate_all
    source_report: dict[str, list[str]] = field(default_factory=dict)

    def model_for(self, vessel_class: str):
        return self.bundles.get(vessel_class.lower())


def get_state(request: Request) -> AppState:
    return request.app.state.freightiq


def get_conn(request: Request) -> sqlite3.Connection:
    return get_state(request).conn


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stale_sources(conn: sqlite3.Connection) -> list[str]:
    from data import cache

    try:
        return cache.stale_sources(conn, config.STALE_AFTER_MINUTES)
    except Exception as exc:  # noqa: BLE001 - status must never break a response
        log.warning("could not read source status: %s", exc)
        return []


def snapshot_provenance(path: Path) -> str | None:
    import json

    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh).get("provenance")
    except (OSError, ValueError):
        return None
