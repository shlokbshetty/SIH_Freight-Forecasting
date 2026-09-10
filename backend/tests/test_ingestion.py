"""Ingestion: failure tolerance, provenance, and the offline guarantee."""

from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from data import cache, ingest
from data.adapters import build_adapters
from data.adapters.base import SourceAdapter, StaleSeriesError, yahoo_close


# ── One dead source must never take down the rest ─────────────────────────────

class ExplodingAdapter(SourceAdapter):
    name = "baltic"          # shadows a namespace that the snapshot fills
    source_label = "deliberately broken"
    is_proxy = True

    def fetch(self):
        raise RuntimeError("simulated outage")


class EmptyAdapter(SourceAdapter):
    name = "equity"
    source_label = "returns nothing"
    is_proxy = True

    def fetch(self):
        return pd.DataFrame(columns=["timestamp", "metric", "value", "source"])


class MalformedAdapter(SourceAdapter):
    name = "macro"
    source_label = "wrong columns"

    def fetch(self):
        return pd.DataFrame({"when": [1], "what": ["x"]})


@pytest.mark.parametrize("broken", [ExplodingAdapter, EmptyAdapter, MalformedAdapter])
def test_a_broken_adapter_degrades_to_cache_and_never_raises(conn, broken):
    outcome = broken().safe_fetch(conn)
    assert outcome.is_stale is True
    assert outcome.error
    # It came back with the snapshot's rows for that namespace rather than nothing.
    assert outcome.rows > 0


def test_refresh_all_completes_past_a_dead_source(conn):
    adapters = [ExplodingAdapter(), _StubAdapter()]
    outcomes = ingest.refresh_all(conn, adapters)
    assert len(outcomes) == 2
    assert outcomes[0].is_stale is True
    assert outcomes[1].is_stale is False


class _StubAdapter(SourceAdapter):
    name = "congestion"
    source_label = "stub"

    def fetch(self):
        return pd.DataFrame({
            "timestamp": [pd.Timestamp(date.today())],
            "metric": ["congestion.Paradip.wait_days"],
            "value": [3.5],
            "source": ["test"],
        })


def test_status_reports_staleness_proxy_and_label(conn):
    ingest.refresh_all(conn, [ExplodingAdapter(), _StubAdapter()])
    by_source = {s["source"]: s for s in cache.read_status(conn, 180)}

    dead = by_source["baltic"]
    assert dead["is_stale"] is True
    assert dead["is_proxy"] is True
    assert "outage" in (dead["error"] or "")

    ok = by_source["congestion"]
    assert ok["is_stale"] is False
    assert ok["age_minutes"] is not None


# ── The offline guarantee ─────────────────────────────────────────────────────

def test_snapshot_seeds_a_cold_cache(cache_db):
    conn = cache.connect(cache_db)
    seeded = ingest.bootstrap(conn)
    assert seeded > 5_000
    assert len(cache.known_metrics(conn)) > 40


def test_reseeding_is_a_no_op(conn):
    assert ingest.bootstrap(conn) == 0


def test_seeded_sources_are_marked_stale_not_live(conn):
    """Seeded data is real in shape but old in time. Presenting it as live would
    be the one thing the whole provenance design exists to prevent."""
    for status in cache.read_status(conn, 180):
        if status["source"] == "freight":
            continue  # derived at bootstrap, not seeded
        assert status["is_stale"] is True


def test_freight_rates_are_derived_from_the_snapshot(conn):
    """Derivation must work offline, or a cold boot has no target series."""
    for vessel_class in ingest.CLASS_DRIVERS:
        row = cache.latest_observation(conn, f"freight.rate.{vessel_class}")
        assert row is not None
        assert row["value"] > 0
        assert row["source"].startswith("derived:")


def test_per_tonne_rates_fall_as_the_ship_gets_bigger(conn):
    """A Capesize spreads one voyage over five times the cargo. Any run where
    Handysize prices below Capesize means the calibration has been inverted."""
    rates = {
        c: cache.latest_observation(conn, f"freight.rate.{c}")["value"]
        for c in ingest.CLASS_DRIVERS
    }
    assert rates["capesize"] < rates["panamax"] < rates["supramax"] < rates["handysize"]


# ── Superseding seeded rows ───────────────────────────────────────────────────

def test_live_data_supersedes_seeded_rows_it_covers(conn):
    metric = "congestion.Paradip.wait_days"
    before = cache.latest_observation(conn, metric)
    assert before["source"].startswith("synthetic:")

    ingest.refresh_all(conn, [_StubAdapter()])

    after = cache.latest_observation(conn, metric)
    assert after["source"] == "test", (
        "a seeded row dated today shadowed the live value; latest_observation "
        "would keep returning fiction after a successful refresh"
    )


def test_seeded_history_before_the_live_window_survives(conn):
    """A live source with a short history must not wipe usable backfill.

    The stub covers a single day. Everything before it has to stay, or three
    years of history would vanish the first time a ticker came back thin.
    """
    metric = "congestion.Paradip.wait_days"
    original = cache.read_observations(conn, metrics=[metric])
    assert len(original) > 30

    ingest.refresh_all(conn, [_StubAdapter()])
    remaining = cache.read_observations(conn, metrics=[metric])

    live = [r for r in remaining if r["source"] == "test"]
    seeded = [r for r in remaining if r["source"].startswith("synthetic:")]
    assert len(live) == 1
    assert len(seeded) > 30, "backfill older than the live window was destroyed"
    assert max(r["timestamp"] for r in seeded) < live[0]["timestamp"]


# ── The staleness guard ───────────────────────────────────────────────────────

def test_a_frozen_series_is_rejected_rather_than_ingested():
    """Yahoo serves the full history of a dead contract, so an emptiness check
    passes it. This is the guard that caught MTF=F, frozen since December 2025."""
    frozen = pd.Series(
        [100.0, 101.0, 102.0],
        index=pd.to_datetime([date.today() - timedelta(days=d) for d in (260, 259, 258)]),
    )

    class _Fake:
        def history(self, **_kw):
            return pd.DataFrame({"Close": frozen})

    import sys
    import types

    from app import config

    sys.modules["yfinance"] = types.SimpleNamespace(Ticker=lambda _t: _Fake())
    offline = config.OFFLINE_MODE
    config.OFFLINE_MODE = False   # the suite runs offline; this one call must go through
    try:
        with pytest.raises(StaleSeriesError):
            yahoo_close("DEAD=F", max_age_days=10)

        # And a current series of the same shape is accepted.
        fresh = pd.Series(
            [100.0, 101.0, 102.0],
            index=pd.to_datetime([date.today() - timedelta(days=d) for d in (3, 2, 1)]),
        )
        _Fake.history = lambda self, **_kw: pd.DataFrame({"Close": fresh})
        assert len(yahoo_close("LIVE=F", max_age_days=10)) == 3
    finally:
        config.OFFLINE_MODE = offline
        del sys.modules["yfinance"]


# ── The AIS adapter, against a file rather than committed fake data ───────────

def test_ais_adapter_derives_corridors_and_draft_distributions(tmp_path: Path):
    from data.adapters.ais import AISAdapter

    corridors = tmp_path / "corridors.json"
    corridors.write_text(json.dumps({"corridors": [
        {"id": "bay_of_bengal", "name": "Bay of Bengal",
         "bbox": {"lat_min": 5, "lat_max": 22.5, "lon_min": 80, "lon_max": 95}},
        {"id": "elsewhere", "name": "Elsewhere",
         "bbox": {"lat_min": 50, "lat_max": 60, "lon_min": -10, "lon_max": 5}},
    ]}))

    positions = tmp_path / "ais.csv"
    with positions.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "VesselType", "Length", "Width", "Draft"])
        for i in range(40):
            # Two hulls per class inside the Bay of Bengal box.
            length, draft = [(180, 9.8), (200, 12.4), (225, 13.8), (295, 17.4)][i % 4]
            w.writerow([100000 + i, "2026-09-01T04:00:00", 15.0, 86.0, 11.5, 70, length, 32, draft])
        # One container ship, which must be filtered out by type.
        w.writerow([999999, "2026-09-01T04:00:00", 15.0, 86.0, 18.0, 80, 300, 40, 14.0])

    frame = AISAdapter(path=positions, corridors=corridors).fetch()
    metrics = set(frame["metric"])

    assert "ais.corridor.bay_of_bengal.vessel_count" in metrics
    count = frame.loc[frame["metric"] == "ais.corridor.bay_of_bengal.vessel_count", "value"].iloc[0]
    assert count == 40, "the container ship should have been filtered out by vessel type"

    empty = frame.loc[frame["metric"] == "ais.corridor.elsewhere.vessel_count", "value"].iloc[0]
    assert empty == 0

    for vessel_class in ("handysize", "supramax", "panamax", "capesize"):
        assert f"ais.draft.{vessel_class}.p50" in metrics


def test_ais_adapter_reports_a_missing_file_rather_than_crashing(tmp_path: Path, conn):
    from data.adapters.ais import AISAdapter

    adapter = AISAdapter(path=tmp_path / "absent.csv", corridors=tmp_path / "absent.json")
    assert adapter.validate(), "a missing AIS file must be reported at startup"
    outcome = adapter.safe_fetch(conn)
    assert outcome.is_stale is True
