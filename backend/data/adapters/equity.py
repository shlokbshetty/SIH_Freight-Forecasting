"""Listed dry-bulk owners as a freight proxy.

Two tickers carry the dry-bulk signal:

    GOGL  Golden Ocean Group. Capesize and Newcastlemax heavy, so it tracks the
          large end of the market more tightly than a blended index does.
    SBLK  Star Bulk Carriers. Mixed fleet with a large Supramax and Ultramax
          component, used for the middle sizes.

ZIM is deliberately **not** in the dry-bulk feature set. It is a container
liner. Container and dry bulk are different markets with different demand
drivers, different vessel supply, and different cycles; feeding ZIM into a
dry-bulk model imports noise dressed as signal. It is carried only as an
optional macro sentiment series, under its own metric, off by default, and
``models/project.py`` never reads it.

Each ticker is probed at startup. Yahoo answers a delisted or renamed symbol
with an empty frame rather than an error, which is how a dead ticker quietly
becomes a column of NaNs.
"""

from __future__ import annotations

import logging
import os

import pandas as pd

from data.adapters.base import SourceAdapter, frame_from_series, probe_ticker, yahoo_close

log = logging.getLogger(__name__)

#: Feeds the dry-bulk model.
DRY_BULK_TICKERS: dict[str, str] = {"gogl": "GOGL", "sblk": "SBLK"}

#: Container liner. Macro sentiment only, never a dry-bulk feature.
MACRO_SENTIMENT_TICKERS: dict[str, str] = {"zim": "ZIM"}


def include_macro_sentiment() -> bool:
    return os.getenv("FREIGHTIQ_INCLUDE_ZIM", "0").strip().lower() in {"1", "true", "yes"}


class EquityProxyAdapter(SourceAdapter):
    name = "equity"
    source_label = "Listed dry-bulk owner equities (GOGL, SBLK)"
    is_proxy = True

    def __init__(self, period: str = "3y") -> None:
        super().__init__()
        self.period = period
        self.healthy: dict[str, str] = dict(DRY_BULK_TICKERS)

    def validate(self) -> list[str]:
        """Probe every ticker, drop the dead ones, report what was dropped."""
        problems: list[str] = []
        healthy: dict[str, str] = {}
        for key, ticker in DRY_BULK_TICKERS.items():
            ok, detail = probe_ticker(ticker)
            if ok:
                healthy[key] = ticker
                log.info("equity proxy %s (%s) healthy: %s", key, ticker, detail)
            else:
                problems.append(f"{ticker} returned no usable data ({detail}); skipping it")
                log.warning("equity proxy %s (%s) unusable: %s", key, ticker, detail)
        self.healthy = healthy
        if not healthy:
            problems.append("no dry-bulk equity proxy is available")
        return problems

    def fetch(self) -> pd.DataFrame:
        wanted = dict(self.healthy or DRY_BULK_TICKERS)
        if include_macro_sentiment():
            wanted.update(MACRO_SENTIMENT_TICKERS)
            self.notes.append("ZIM included as macro sentiment only; excluded from dry-bulk features")

        frames: list[pd.DataFrame] = []
        for key, ticker in wanted.items():
            try:
                series = yahoo_close(ticker, self.period)
            except Exception as exc:  # noqa: BLE001 - isolate per ticker
                log.warning("equity %s (%s) unavailable: %s", key, ticker, exc)
                self.notes.append(f"{ticker} unavailable this run")
                continue
            frames.append(frame_from_series(series, f"equity.{key}", f"yahoo:{ticker}"))

        if not frames:
            raise ValueError("no equity proxy returned data")
        return pd.concat(frames, ignore_index=True)
