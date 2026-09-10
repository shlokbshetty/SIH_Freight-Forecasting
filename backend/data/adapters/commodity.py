"""Thermal coal and iron ore, the two commodities that set dry-bulk demand.

Futures first, FRED as the fallback. Each ticker is probed rather than trusted,
because Yahoo answers a dead contract symbol with an empty frame, not an error.

The FRED coal series is monthly. It is resampled to daily by time interpolation
and the raw monthly prints are cached alongside it, so nothing is silently
forward-filled into a staircase the model would read as shocks.
"""

from __future__ import annotations

import logging

import pandas as pd

from data.adapters import fred
from data.adapters.base import SourceAdapter, frame_from_series, probe_ticker, yahoo_close

log = logging.getLogger(__name__)

#: metric -> Yahoo futures symbol.
#:
#: MTF=F (Coal API2 CIF ARA) is kept but rarely works: the contract stopped
#: printing in December 2025 and Yahoo still serves its frozen history, which
#: the staleness guard in base.py rejects. FRED is the coal path that actually
#: runs. It stays listed so the probe reports on it rather than the symbol
#: quietly disappearing from the codebase.
FUTURES: dict[str, str] = {
    "commodity.coal.api2": "MTF=F",       # Coal API2 CIF ARA, USD/tonne
    "commodity.iron_ore.62fe": "TIO=F",   # Iron ore 62% Fe CFR China, USD/tonne
}

#: Global price of coal, Australia. Monthly, USD/tonne. The fallback when the
#: coal future is unavailable, and the closest free series to the Newcastle
#: benchmark that actually prices Australian coal into India.
FRED_COAL_SERIES = "PCOALAUUSDM"

#: Newcastle 6000 kcal has no free feed. Carried as API2 plus a differential,
#: which is crude but stated rather than hidden.
NEWCASTLE_OVER_API2_USD = 31.0


class CommodityAdapter(SourceAdapter):
    name = "commodity"
    source_label = "Coal and iron ore futures (Yahoo), with FRED PCOALAUUSDM fallback"
    is_proxy = False

    def __init__(self) -> None:
        super().__init__()
        self.healthy: dict[str, str] = dict(FUTURES)

    def validate(self) -> list[str]:
        problems: list[str] = []
        healthy: dict[str, str] = {}
        for metric, ticker in FUTURES.items():
            ok, detail = probe_ticker(ticker)
            if ok:
                healthy[metric] = ticker
                log.info("commodity %s (%s) healthy: %s", metric, ticker, detail)
            else:
                problems.append(f"{ticker} for {metric} returned no usable data ({detail})")
                log.warning("commodity %s (%s) unusable: %s", metric, ticker, detail)
        self.healthy = healthy
        if "commodity.coal.api2" not in healthy:
            problems.append(f"coal future unavailable; will fall back to FRED {FRED_COAL_SERIES}")
        return problems

    def fetch(self) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        api2: pd.Series | None = None
        wanted = self.healthy if self.healthy else FUTURES

        for metric, ticker in wanted.items():
            try:
                series = yahoo_close(ticker)
            except Exception as exc:  # noqa: BLE001 - isolate per ticker
                log.warning("commodity %s (%s) unavailable: %s", metric, ticker, exc)
                self.notes.append(f"{ticker} unavailable this run")
                continue
            if metric == "commodity.coal.api2":
                api2 = series
            frames.append(frame_from_series(series, metric, f"yahoo:{ticker}"))

        # Coal fallback. Cache the monthly truth and an explicitly interpolated
        # daily series; the feature frame reads the daily one.
        if api2 is None:
            try:
                monthly, label = fred.get_series(FRED_COAL_SERIES)
                frames.append(frame_from_series(monthly, "commodity.coal.au_monthly", label))
                daily, note = fred.to_daily(monthly, FRED_COAL_SERIES)
                frames.append(
                    frame_from_series(daily, "commodity.coal.au_daily", f"{label}:interpolated")
                )
                self.notes.append(note)
                self.notes.append("coal future unavailable; using FRED Australia coal instead")
                api2 = daily
            except Exception as exc:  # noqa: BLE001
                log.warning("FRED coal fallback failed: %s", exc)
                self.notes.append(f"FRED coal fallback failed: {exc}")

        if api2 is not None:
            frames.append(
                frame_from_series(
                    api2 + NEWCASTLE_OVER_API2_USD,
                    "commodity.coal.newcastle",
                    f"derived:+{NEWCASTLE_OVER_API2_USD:.0f}USD",
                )
            )

        if not frames:
            raise ValueError("no commodity source returned data")
        return pd.concat(frames, ignore_index=True)
