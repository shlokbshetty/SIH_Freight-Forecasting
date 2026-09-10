"""Port congestion from a committed JSON file.

No free port-queue or anchorage-count API exists.

MarineTraffic and VesselFinder are explicitly **not** scraped. Both prohibit it
in their terms, both block bots, and a scraper that works today becomes a silent
source of wrong numbers the day their markup changes. A stub that is honest
about being a stub is worth more than a scraper that is quietly broken.

The interface matches every other adapter, so a paid AIS or port-agent feed
replaces the body of ``fetch`` and nothing else.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from app import config
from data.adapters.base import SourceAdapter

log = logging.getLogger(__name__)


class CongestionAdapter(SourceAdapter):
    name = "congestion"
    source_label = "Committed anchorage counts (manual, port-agent sourced)"
    is_proxy = True

    def __init__(self, path: Path | None = None) -> None:
        super().__init__()
        self.path = path or config.CONGESTION_FILE

    def validate(self) -> list[str]:
        if not self.path.exists():
            return [f"congestion file {self.path} is missing"]
        return []

    def fetch(self) -> pd.DataFrame:
        if not self.path.exists():
            raise FileNotFoundError(f"congestion file {self.path} not found")

        with self.path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)

        observed = payload.get("observed_at") or date.today().isoformat()
        provider = payload.get("provider", "committed-json")
        stamp = pd.to_datetime(observed)

        rows: list[dict] = []
        for port_id, entry in (payload.get("ports") or {}).items():
            if not isinstance(entry, dict):
                continue
            for field, metric in (
                ("vessels_at_anchor", "vessels_at_anchor"),
                ("wait_days", "wait_days"),
                ("berths_available", "berths_available"),
            ):
                value = entry.get(field)
                if value is None:
                    continue
                rows.append(
                    {
                        "timestamp": stamp,
                        "metric": f"congestion.{port_id}.{metric}",
                        "value": float(value),
                        "source": provider,
                    }
                )

        if not rows:
            raise ValueError("congestion file contained no port entries")

        age_days = (pd.Timestamp(date.today()) - stamp).days
        if age_days > 7:
            self.notes.append(f"anchorage counts were observed {age_days} days ago")
        return pd.DataFrame(rows)
