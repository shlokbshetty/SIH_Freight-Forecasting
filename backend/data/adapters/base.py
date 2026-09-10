"""Adapter contract.

Every source implements::

    class SourceAdapter:
        name: str            # metric namespace and status key
        source_label: str    # what a human should be told this is
        is_proxy: bool       # True when it stands in for something else
        def fetch(self) -> pd.DataFrame   # [timestamp, metric, value, source]

``fetch`` may raise. Callers use :meth:`safe_fetch`, which never does: on any
failure it logs a warning, reads that adapter's last values back out of SQLite,
and returns them marked stale. One dead source degrades to old numbers with a
visible flag. It cannot take out ingestion, the API, or a screen.

``is_proxy`` is not decoration. Two of these sources are not the thing they are
named after: the Baltic series is a contract-for-difference quote, not the
licensed index, and there is no free bunker feed at all. Both are surfaced
through /api/data/status so the UI can say so rather than implying an
authority the number does not have.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from app import config
from data import cache

log = logging.getLogger(__name__)

FRAME_COLUMNS = ["timestamp", "metric", "value", "source"]

USER_AGENT = "FreightIQ/1.0 (SIH freight forecasting; contact: repo owner)"

#: A daily market series whose newest point is older than this is not current,
#: whatever it says on the tin.
#:
#: This guard exists because of a real failure. The Yahoo symbol MTF=F for API2
#: coal still returns 578 points of history, so an emptiness check passes it
#: cleanly, but it stopped updating in December 2025. Ingesting it would have
#: fed the model nine-month-old coal prices as today's, which is worse than
#: having no coal series at all: a missing source is visible, a frozen one is
#: not.
MAX_SERIES_AGE_DAYS = 10


class StaleSeriesError(ValueError):
    """A series returned data, but the data stopped some time ago."""


def empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=FRAME_COLUMNS)


class OfflineError(RuntimeError):
    """Raised when config.OFFLINE_MODE forbids an outbound call."""


def http_get(url: str, params: dict | None = None, *, as_json: bool = True):
    """Small stdlib GET. Avoids an HTTP client dependency for a handful of calls."""
    if config.OFFLINE_MODE:
        raise OfflineError("offline mode is on")
    full = url
    if params:
        full = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
    req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=config.HTTP_TIMEOUT_SECONDS) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if as_json else raw


def yahoo_close(ticker: str, period: str = "3y", max_age_days: int = MAX_SERIES_AGE_DAYS) -> pd.Series:
    """Daily closes for one ticker, rejected if they have stopped updating.

    yfinance is imported lazily so that a missing or broken install degrades the
    adapter that uses it rather than breaking module import for everything.
    """
    if config.OFFLINE_MODE:
        raise OfflineError("offline mode is on")
    import yfinance as yf  # noqa: PLC0415

    hist = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True)
    if hist is None or hist.empty or "Close" not in hist:
        raise ValueError(f"no close data for {ticker}")
    close = hist["Close"].dropna()
    if close.empty:
        raise ValueError(f"empty close series for {ticker}")
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()

    age = (pd.Timestamp(date.today()) - close.index[-1]).days
    if max_age_days is not None and age > max_age_days:
        raise StaleSeriesError(
            f"{ticker} last traded {close.index[-1].date()}, {age} days ago; "
            f"treating it as dead rather than current"
        )
    return close


def probe_ticker(ticker: str, period: str = "3y") -> tuple[bool, str]:
    """Does this ticker return current, usable data? Used at startup.

    Probes over the same window the adapter will actually fetch. Probing a short
    window and fetching a long one is how a dead contract slips through: the
    short probe finds nothing and is treated as a transient miss, while the long
    fetch happily returns years of frozen history.
    """
    try:
        series = yahoo_close(ticker, period=period)
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    if len(series) < 20:
        return False, f"only {len(series)} observations over {period}"

    span_days = (series.index[-1] - series.index[0]).days
    detail = f"{len(series)} observations, {series.index[0].date()} to {series.index[-1].date()}"
    if span_days < 200:
        return True, f"{detail} — SHORT HISTORY, only {span_days} days"
    return True, detail


def frame_from_series(series: pd.Series, metric: str, source: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": series.index,
            "metric": metric,
            "value": series.to_numpy(dtype=float),
            "source": source,
        }
    )


@dataclass
class FetchOutcome:
    adapter: str
    frame: pd.DataFrame
    is_stale: bool
    error: str | None = None
    notes: list[str] | None = None

    @property
    def rows(self) -> int:
        return int(len(self.frame))


class SourceAdapter(ABC):
    name: str = "source"
    source_label: str = "unnamed source"
    is_proxy: bool = False

    #: Set by fetch() when it wants to say something the log alone would lose,
    #: for instance that a monthly series was resampled.
    notes: list[str]

    def __init__(self) -> None:
        self.notes = []

    @abstractmethod
    def fetch(self) -> pd.DataFrame:
        """Pull fresh data. May raise; callers use ``safe_fetch``."""

    def validate(self) -> list[str]:
        """Startup check. Return a list of problems; empty means healthy.

        Runs before the first refresh so a dead ticker is reported once, loudly,
        instead of turning into silent NaNs downstream.
        """
        return []

    # -- failure tolerance ----------------------------------------------------

    def cached_frame(self, conn: sqlite3.Connection, lookback_days: int = 1_200) -> pd.DataFrame:
        since = (date.today() - timedelta(days=lookback_days)).isoformat()
        rows = [
            r for r in cache.read_observations(conn, since=since)
            if cache.adapter_for_metric(r["metric"]) == self.name
        ]
        if not rows:
            return empty_frame()
        return pd.DataFrame(
            {
                "timestamp": pd.to_datetime([r["timestamp"] for r in rows]),
                "metric": [r["metric"] for r in rows],
                "value": [r["value"] for r in rows],
                "source": [r["source"] for r in rows],
            }
        )

    def safe_fetch(self, conn: sqlite3.Connection) -> FetchOutcome:
        self.notes = []
        try:
            frame = self.fetch()
            if frame is None or frame.empty:
                raise ValueError("adapter returned no rows")
            missing = set(FRAME_COLUMNS) - set(frame.columns)
            if missing:
                raise ValueError(f"frame missing columns: {sorted(missing)}")
            return FetchOutcome(self.name, frame[FRAME_COLUMNS], False, None, list(self.notes))
        except Exception as exc:  # noqa: BLE001 - one dead source must not spread
            log.warning(
                "source %r failed (%s: %s); falling back to cache",
                self.name, type(exc).__name__, exc,
            )
            return FetchOutcome(
                self.name, self.cached_frame(conn), True,
                f"{type(exc).__name__}: {exc}", list(self.notes),
            )
