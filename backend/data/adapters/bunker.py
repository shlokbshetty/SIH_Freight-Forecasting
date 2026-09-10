"""Bunker prices from a committed CSV.

There is no free live bunker feed. Ship & Bunker and Argus both publish behind a
licence, and their web pages are not an API. So this reads a committed file of
VLSFO levels for Singapore and Rotterdam.

The interface is identical to every other adapter on purpose: when a paid feed
is bought, it replaces the body of ``fetch`` and nothing else in the system
changes. Until then the values are marked indicative and ``is_proxy`` is True,
so the dashboard says what they are.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import pandas as pd

from app import config
from data.adapters.base import SourceAdapter

log = logging.getLogger(__name__)

EXPECTED_COLUMNS = {"date", "port", "grade", "price_usd_per_t"}


class BunkerAdapter(SourceAdapter):
    name = "bunker"
    source_label = "Committed VLSFO reference levels (Singapore, Rotterdam)"
    is_proxy = True

    def __init__(self, path: Path | None = None) -> None:
        super().__init__()
        self.path = path or config.BUNKER_CSV

    def validate(self) -> list[str]:
        if not self.path.exists():
            return [f"bunker reference file {self.path} is missing"]
        return []

    def fetch(self) -> pd.DataFrame:
        if not self.path.exists():
            raise FileNotFoundError(f"bunker reference file {self.path} not found")

        rows: list[dict] = []
        indicative = 0
        with self.path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            missing = EXPECTED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"bunker CSV missing columns {sorted(missing)}")
            for line, row in enumerate(reader, start=2):
                try:
                    price = float(row["price_usd_per_t"])
                except (TypeError, ValueError):
                    log.warning("skipping %s line %s: unparseable price", self.path.name, line)
                    continue
                port = row["port"].strip().lower()
                grade = row["grade"].strip().lower()
                is_indicative = str(row.get("is_indicative", "1")).strip() in {"1", "true", "yes"}
                indicative += int(is_indicative)
                rows.append(
                    {
                        "timestamp": pd.to_datetime(row["date"]),
                        "metric": f"bunker.{grade}.{port}",
                        "value": price,
                        "source": row.get("source", "committed-csv")
                        + (":indicative" if is_indicative else ":quoted"),
                    }
                )

        if not rows:
            raise ValueError("bunker CSV contained no usable rows")

        frame = pd.DataFrame(rows)
        if indicative:
            self.notes.append(
                f"{indicative} of {len(rows)} bunker rows are indicative levels, not broker quotes"
            )
        # The file is monthly. Say so rather than letting a daily join imply
        # daily observation.
        self.notes.append(
            "bunker levels are month-end reference points; the feature frame interpolates between them"
        )
        return frame
