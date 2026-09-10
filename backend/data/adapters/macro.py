"""Macro series from FRED.

    DEXINUS  Indian rupees per US dollar, daily. Freight is quoted in dollars
             and the procurement budget is in rupees, so the exchange rate is a
             first-order driver of landed cost, not background colour.
    DEXUSAL  US dollars per Australian dollar, daily. Moves with the terms of
             trade on the Australian coal lane.

The key comes from FRED_API_KEY in the environment and is never read from
source. Without a key the public fredgraph endpoint serves the same series.
"""

from __future__ import annotations

import logging

import pandas as pd

from data.adapters import fred
from data.adapters.base import SourceAdapter, frame_from_series

log = logging.getLogger(__name__)

SERIES: dict[str, str] = {
    "macro.usdinr": "DEXINUS",
    "macro.audusd": "DEXUSAL",
}


class MacroAdapter(SourceAdapter):
    name = "macro"
    source_label = "FRED macro series (DEXINUS, DEXUSAL)"
    is_proxy = False

    def validate(self) -> list[str]:
        if not fred.api_key():
            return ["FRED_API_KEY not set; using the public fredgraph endpoint"]
        return []

    def fetch(self) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for metric, series_id in SERIES.items():
            try:
                series, label = fred.get_series(series_id)
            except Exception as exc:  # noqa: BLE001 - isolate per series
                log.warning("macro %s (%s) unavailable: %s", metric, series_id, exc)
                self.notes.append(f"{series_id} unavailable this run")
                continue
            frames.append(frame_from_series(series, metric, label))

        if not frames:
            raise ValueError("no macro series returned data")
        return pd.concat(frames, ignore_index=True)
