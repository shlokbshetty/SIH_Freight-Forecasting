"""FRED access, with and without an API key.

``fredapi`` is used when ``FRED_API_KEY`` is present in the environment. When it
is not, the public ``fredgraph.csv`` endpoint serves the same series without any
credential, which is what keeps the no-paid-keys constraint honest rather than
aspirational. No key is ever read from source.
"""

from __future__ import annotations

import csv
import io
import logging
import os

import pandas as pd

from data.adapters.base import http_get

log = logging.getLogger(__name__)

FREDGRAPH_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"

#: FRED serves the whole series, and DEXINUS starts in 1973. Ingesting fifty
#: years of daily history to model the next six months bloats the cache and the
#: committed snapshot for nothing.
DEFAULT_LOOKBACK_DAYS = 1_825


def api_key() -> str | None:
    key = os.getenv("FRED_API_KEY")
    return key.strip() if key and key.strip() else None


def _via_fredapi(series_id: str) -> pd.Series:
    from fredapi import Fred  # noqa: PLC0415

    series = Fred(api_key=api_key()).get_series(series_id)
    series = series.dropna()
    series.index = pd.to_datetime(series.index).normalize()
    return series.astype(float)


def _via_public_csv(series_id: str) -> pd.Series:
    raw = http_get(FREDGRAPH_CSV, {"id": series_id}, as_json=False)
    reader = csv.reader(io.StringIO(raw))
    header = next(reader, None)
    if not header or len(header) < 2:
        raise ValueError(f"unexpected fredgraph header for {series_id}: {header}")

    stamps: list[str] = []
    values: list[float] = []
    for row in reader:
        if len(row) < 2:
            continue
        # FRED writes "." for a missing observation.
        if row[1].strip() in {".", ""}:
            continue
        try:
            values.append(float(row[1]))
        except ValueError:
            continue
        stamps.append(row[0])

    if not values:
        raise ValueError(f"no usable observations for {series_id}")
    return pd.Series(values, index=pd.to_datetime(stamps).normalize()).astype(float)


def get_series(series_id: str, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> tuple[pd.Series, str]:
    """Returns the series and a label saying how it was obtained."""
    series: pd.Series
    label: str
    if api_key():
        try:
            series, label = _via_fredapi(series_id), f"fred:{series_id}:api"
        except Exception as exc:  # noqa: BLE001 - the public endpoint still works
            log.warning("fredapi failed for %s (%s); trying the public CSV", series_id, exc)
            series, label = _via_public_csv(series_id), f"fred:{series_id}:public"
    else:
        series, label = _via_public_csv(series_id), f"fred:{series_id}:public"

    if lookback_days:
        cutoff = pd.Timestamp.today().normalize() - pd.Timedelta(days=lookback_days)
        trimmed = series[series.index >= cutoff]
        if not trimmed.empty:
            series = trimmed
    return series, label


def to_daily(series: pd.Series, series_id: str) -> tuple[pd.Series, str]:
    """Upsample a monthly series to daily by time interpolation.

    Deliberately not a forward fill. A forward fill would hold January's price
    flat for thirty-one days and then step, which hands the model a staircase it
    reads as thirty-one days of calm followed by a shock. Linear interpolation
    in time spreads the move, which is closer to how the underlying market got
    from one print to the next.

    The raw monthly observations are cached alongside this, so nothing is lost.
    """
    if series.empty:
        return series, ""
    daily_index = pd.date_range(series.index.min(), series.index.max(), freq="D")
    daily = series.reindex(series.index.union(daily_index)).interpolate(method="time")
    daily = daily.reindex(daily_index).dropna()
    note = (
        f"{series_id} is published monthly ({len(series)} prints); "
        f"resampled to {len(daily)} daily points by time interpolation, not forward fill"
    )
    return daily, note
