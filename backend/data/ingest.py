"""Ingestion orchestration.

The adapters live in ``data/adapters/``. This module runs them, persists what
comes back, records per-source status, and derives the freight rates the model
targets.

Architecture rule, enforced here: nothing in a request path calls any of this.
The scheduler calls :func:`refresh_all` on a timer, API handlers read only from
the SQLite cache, and :func:`bootstrap` seeds that cache from the committed
snapshot so a cold, network-free boot serves every screen.
"""

from __future__ import annotations

import logging
import sqlite3

import pandas as pd

from app import config
from data import cache
from data.adapters import FetchOutcome, SourceAdapter, adapter_metadata, build_adapters, validate_all

log = logging.getLogger(__name__)

__all__ = ["refresh_all", "bootstrap", "validate_all", "derive_freight_rates"]


# ── Derived freight rates ─────────────────────────────────────────────────────
#
# The model targets a route rate in dollars per tonne. No free source publishes
# one, so it is derived from the proxies that are free, and the derivation is
# kept in the open rather than hidden inside a pickle.
#
#     rate = base_usd_per_t * (driver / median(driver)) ** beta
#
# Calibrating against the driver's own median rather than a hardcoded reference
# level means the mapping does not drift as the proxy re-rates, which a fixed
# reference silently would.

#: vessel class -> (driver metric, beta, base USD/tonne, why this driver)
CLASS_DRIVERS: dict[str, tuple[str, float, float, str]] = {
    "capesize": ("equity.gogl", 1.00, 12.5, "Golden Ocean is Capesize and Newcastlemax heavy"),
    "panamax": ("baltic.bdi", 0.85, 15.5, "BDI's front basket is Panamax weighted"),
    "supramax": ("equity.sblk", 0.70, 18.5, "Star Bulk skews Supramax and Ultramax"),
    "handysize": ("equity.sblk", 0.55, 23.0, "no listed Handysize pure play; damped Supramax signal"),
}

#: Tried in order when a class's preferred driver has no data.
DRIVER_FALLBACKS = ["baltic.bdi", "equity.gogl", "equity.sblk"]


def _series_for(conn: sqlite3.Connection, metric: str) -> pd.Series | None:
    rows = cache.read_observations(conn, metrics=[metric])
    if not rows:
        return None
    series = pd.Series(
        [float(r["value"]) for r in rows],
        index=pd.to_datetime([r["timestamp"] for r in rows]),
    ).sort_index()
    return series if len(series) >= 30 else None


def derive_freight_rates(conn: sqlite3.Connection) -> int:
    """Write ``freight.rate.<class>`` from whichever proxies are available."""
    written = 0
    used: list[str] = []

    for vessel_class, (preferred, beta, base, _why) in CLASS_DRIVERS.items():
        series = _series_for(conn, preferred)
        driver = preferred
        if series is None:
            for candidate in DRIVER_FALLBACKS:
                series = _series_for(conn, candidate)
                if series is not None:
                    driver = candidate
                    log.info("%s: %s unavailable, driving off %s", vessel_class, preferred, candidate)
                    break
        if series is None:
            log.warning("%s: no driver series available; freight rate not derived", vessel_class)
            continue

        anchor = float(series.median())
        if anchor <= 0:
            continue
        rate = base * (series / anchor) ** beta
        written += cache.write_observations(
            conn,
            [
                (f"freight.rate.{vessel_class}", ts.date().isoformat(), float(v), f"derived:{driver}")
                for ts, v in rate.items()
                if pd.notna(v)
            ],
        )
        used.append(f"{vessel_class}<-{driver}")

    if written:
        cache.write_status(
            conn, "freight",
            is_stale=False, row_count=written, succeeded=True, is_proxy=True,
            source_label="Route rates derived from the BDI and equity proxies",
            notes=used,
        )
    return written


# ── Orchestration ─────────────────────────────────────────────────────────────

def _to_observations(frame: pd.DataFrame) -> list[cache.Observation]:
    if frame.empty:
        return []
    stamps = pd.to_datetime(frame["timestamp"]).dt.strftime("%Y-%m-%d")
    return [
        (str(metric), str(ts), float(value), str(source))
        for ts, metric, value, source in zip(
            stamps, frame["metric"], frame["value"], frame["source"]
        )
        if pd.notna(value)
    ]


def _supersede_seeded(conn: sqlite3.Connection, frame: pd.DataFrame) -> tuple[int, list[str]]:
    """Retire seeded rows that a live pull has just covered.

    Returns the number purged and the metrics where live coverage is shorter
    than the seeded history, so the caller can say the series is part backfill
    rather than letting the join look uniform.
    """
    if frame.empty:
        return 0, []

    stamps = pd.to_datetime(frame["timestamp"]).dt.strftime("%Y-%m-%d")
    purged = 0
    backfilled: list[str] = []

    for metric, group in pd.DataFrame({"metric": frame["metric"], "ts": stamps}).groupby("metric"):
        low, high = group["ts"].min(), group["ts"].max()
        purged += cache.purge_seeded(conn, str(metric), low, high)
        remaining = cache.read_observations(conn, metrics=[str(metric)])
        if remaining and remaining[0]["timestamp"] < low:
            backfilled.append(str(metric))

    return purged, backfilled


def refresh_all(
    conn: sqlite3.Connection,
    adapters: list[SourceAdapter] | None = None,
) -> list[FetchOutcome]:
    """Run every adapter, persist, record status, then derive the rates.

    Always returns one outcome per adapter and never raises, whatever the state
    of the network.
    """
    meta = adapter_metadata()
    outcomes: list[FetchOutcome] = []

    for adapter in adapters or build_adapters():
        outcome = adapter.safe_fetch(conn)
        written = 0
        try:
            if not outcome.is_stale:
                purged, backfilled = _supersede_seeded(conn, outcome.frame)
                if purged:
                    log.info("%s: retired %s seeded rows now covered by live data", adapter.name, purged)
                if backfilled:
                    outcome.notes = (outcome.notes or []) + [
                        f"live history is shorter than the snapshot for {len(backfilled)} metric(s); "
                        "earlier points remain seeded backfill"
                    ]
            written = cache.write_observations(conn, _to_observations(outcome.frame))
        except Exception as exc:  # noqa: BLE001 - a write failure is not fatal either
            log.warning("could not persist rows for %r: %s", adapter.name, exc)
            outcome = FetchOutcome(adapter.name, outcome.frame, True, f"write failed: {exc}", outcome.notes)

        info = meta.get(adapter.name, {})
        cache.write_status(
            conn,
            adapter.name,
            is_stale=outcome.is_stale,
            error=outcome.error,
            row_count=written or outcome.rows,
            succeeded=not outcome.is_stale,
            is_proxy=bool(info.get("is_proxy", adapter.is_proxy)),
            source_label=info.get("source_label", adapter.source_label),
            notes=outcome.notes,
        )
        log.info(
            "refreshed %-11s rows=%-6s stale=%s%s",
            adapter.name, written, outcome.is_stale,
            f" error={outcome.error}" if outcome.error else "",
        )
        outcomes.append(outcome)

    try:
        derived = derive_freight_rates(conn)
        if derived:
            log.info("derived %s freight rate observations", derived)
    except Exception as exc:  # noqa: BLE001
        log.warning("freight rate derivation failed: %s", exc)

    return outcomes


def bootstrap(conn: sqlite3.Connection) -> int:
    """Seed the cache from the committed snapshot. Called once at startup."""
    seeded = cache.seed_from_snapshot(conn, config.SNAPSHOT_FILE)
    if not seeded:
        return 0

    # The cache layer knows nothing about adapters, so stamp the proxy flags and
    # labels on now. Without this a seeded Baltic row would report itself as an
    # authoritative index rather than the CFD quote it is.
    meta = adapter_metadata()
    for adapter_name, info in meta.items():
        rows = cache.count_for_source(conn, f"{adapter_name}.")
        if rows:
            cache.write_status(
                conn, adapter_name,
                is_stale=True, error="seeded from snapshot", row_count=rows, succeeded=False,
                is_proxy=bool(info["is_proxy"]), source_label=info["source_label"],
                notes=["values come from the committed snapshot, not a live fetch"],
            )

    try:
        derive_freight_rates(conn)
    except Exception as exc:  # noqa: BLE001
        log.warning("could not derive rates from the snapshot: %s", exc)
    return seeded
