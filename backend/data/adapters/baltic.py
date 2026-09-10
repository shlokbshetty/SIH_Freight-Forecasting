"""Baltic Dry Index proxy.

The Baltic Exchange licenses its indices and there is no free feed of the real
assessment. This adapter carries the closest free instrument instead, and never
claims to be the index itself: ``is_proxy`` is True, the source label says what
it is, and /api/data/status surfaces both.

Primary source, free and unauthenticated:

    BDRY  Breakwave Dry Bulk Shipping ETF. Holds a rolling basket of near-dated
          Capesize, Panamax and Supramax freight futures, which is why it tracks
          the index rather than merely correlating with it. The best public read
          on dry-bulk freight available without a licence.

Optional upgrade, when a key is present:

    TradingEconomics BDIY:IND, the CFD that quotes the index directly. Their
    guest credential was discontinued and every endpoint now answers HTTP 410,
    so this path is only attempted when TRADINGECONOMICS_KEY is set.
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta

import pandas as pd

from data.adapters.base import (
    SourceAdapter,
    frame_from_series,
    http_get,
    probe_ticker,
    yahoo_close,
)

log = logging.getLogger(__name__)

BDRY_TICKER = "BDRY"

TE_HISTORICAL = "https://api.tradingeconomics.com/markets/historical/{symbol}"
TE_SYMBOL = "BDIY:IND"

#: The ETF trades in dollars, the index in points. Scaling the ETF onto the
#: index's own range keeps the published number recognisable to anyone who reads
#: the Baltic daily. The shape carries the signal; this only sets the units.
BDI_REFERENCE_LEVEL = 1_650.0


def te_key() -> str | None:
    key = os.getenv("TRADINGECONOMICS_KEY")
    return key.strip() if key and key.strip() else None


class BalticAdapter(SourceAdapter):
    name = "baltic"
    source_label = "BDRY dry-bulk freight-futures ETF, scaled as a Baltic Dry proxy"
    is_proxy = True

    def __init__(self, lookback_days: int = 1_095) -> None:
        super().__init__()
        self.lookback_days = lookback_days

    def validate(self) -> list[str]:
        problems: list[str] = []
        ok, detail = probe_ticker(BDRY_TICKER)
        if not ok:
            problems.append(f"{BDRY_TICKER} returned no usable data ({detail})")
        else:
            log.info("baltic proxy %s healthy: %s", BDRY_TICKER, detail)
        if not te_key():
            problems.append(
                "no TRADINGECONOMICS_KEY, so the index CFD is unavailable and the "
                "BDRY ETF stands in. Their guest credential was discontinued."
            )
        return problems

    # -- optional licensed path ----------------------------------------------

    def _from_tradingeconomics(self) -> pd.DataFrame | None:
        key = te_key()
        if not key:
            return None
        end = date.today()
        start = end - timedelta(days=self.lookback_days)
        try:
            payload = http_get(
                TE_HISTORICAL.format(symbol=TE_SYMBOL),
                {"c": key, "d1": start.isoformat(), "d2": end.isoformat(), "f": "json"},
            )
        except Exception as exc:  # noqa: BLE001 - fall through to the ETF
            log.warning("TradingEconomics unavailable (%s); using the BDRY proxy", exc)
            return None

        if not isinstance(payload, list) or not payload:
            return None

        stamps, values = [], []
        for row in payload:
            stamp = row.get("Date") or row.get("date")
            close = row.get("Close", row.get("close"))
            if stamp is None or close is None:
                continue
            try:
                values.append(float(close))
            except (TypeError, ValueError):
                continue
            stamps.append(stamp)

        if not values:
            return None

        self.notes.append("BDI from the TradingEconomics CFD, which tracks the licensed index")
        return pd.DataFrame(
            {
                "timestamp": pd.to_datetime(stamps).normalize(),
                "metric": "baltic.bdi",
                "value": values,
                "source": f"tradingeconomics:{TE_SYMBOL}:cfd",
            }
        )

    # -- free path ------------------------------------------------------------

    def fetch(self) -> pd.DataFrame:
        licensed = self._from_tradingeconomics()
        if licensed is not None:
            return licensed

        etf = yahoo_close(BDRY_TICKER)
        scaled = etf * (BDI_REFERENCE_LEVEL / float(etf.median()))

        self.notes.append(
            "BDI proxied by the BDRY freight-futures ETF and scaled to index units; "
            "it is not a Baltic Exchange assessment"
        )
        return pd.concat(
            [
                frame_from_series(scaled, "baltic.bdi", f"yahoo:{BDRY_TICKER}:scaled"),
                frame_from_series(etf, "baltic.bdry_usd", f"yahoo:{BDRY_TICKER}"),
            ],
            ignore_index=True,
        )
