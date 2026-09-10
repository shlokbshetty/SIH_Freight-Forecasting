#!/usr/bin/env python3
"""Generate the committed offline snapshot.

This writes ``data/snapshot.json``, the file the app seeds its cache from on a
cold boot so every screen renders with no network at all.

Two ways to produce that file:

* ``scripts/refresh_snapshot.py`` pulls the real series from the live adapters.
  Use this whenever the machine has market access. It is the preferred path.
* This script synthesises a calibrated baseline using nothing but the standard
  library. Use it to bootstrap a repo, in CI, or on a machine that cannot reach
  Yahoo Finance. The levels and volatilities are set to plausible market values
  and the cross-correlations are real, so the projection model has genuine
  signal to fit, but the numbers are *not* market observations.

The provenance field in the output records which of the two produced it, and
/api/data/status reports every seeded source as stale, so a synthetic baseline
can never be mistaken for live data in the UI.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = BACKEND_ROOT / "data" / "snapshot.json"

DISCHARGE_PORTS = ["Paradip", "Visakhapatnam", "Gangavaram", "Dhamra", "Gopalpur", "Haldia", "Sandheads"]

#: Baseline congestion, in expected waiting days beyond laytime.
PORT_BASE_WAIT = {
    "Paradip": 2.9, "Visakhapatnam": 1.2, "Gangavaram": 1.1, "Dhamra": 1.4,
    "Gopalpur": 3.1, "Haldia": 5.2, "Sandheads": 5.6,
}
PORT_BASE_ANCHORED = {
    "Paradip": 6, "Visakhapatnam": 2, "Gangavaram": 2, "Dhamra": 2,
    "Gopalpur": 4, "Haldia": 9, "Sandheads": 11,
}

#: Listed proxies. BDI is the CFD level; the equities are share prices.
PROXY_BASE = {"baltic.bdi": 1_650.0, "equity.gogl": 12.1, "equity.sblk": 20.3}
PROXY_BETA = {"baltic.bdi": 1.45, "equity.gogl": 1.30, "equity.sblk": 1.05}

BUNKER_BASE = {"bunker.vlsfo.singapore": 604.0, "bunker.vlsfo.rotterdam": 561.0}

COMMODITY_BASE = {
    "commodity.coal.api2": 108.0,
    "commodity.coal.newcastle": 139.0,
    "commodity.iron_ore.62fe": 104.0,
}

#: Rupees per dollar, and dollars per Australian dollar.
MACRO_BASE = {"macro.usdinr": 88.4, "macro.audusd": 0.663}

#: Corridors mirror data/reference/corridors.json.
CORRIDORS = ["au_east_to_eci", "indonesia_to_eci", "moz_to_eci", "bay_of_bengal", "eci_anchorages"]
CORRIDOR_BASE_COUNT = {
    "au_east_to_eci": 41, "indonesia_to_eci": 33, "moz_to_eci": 12,
    "bay_of_bengal": 58, "eci_anchorages": 27,
}

#: Median sailing draft by class, from what ships of that size actually load.
AIS_DRAFT = {
    "handysize": (9.6, 10.3), "supramax": (12.1, 12.9),
    "panamax": (13.4, 14.1), "capesize": (17.0, 17.9),
}
AIS_HULLS = {"handysize": 410, "supramax": 620, "panamax": 380, "capesize": 240}


def is_business_day(d: date) -> bool:
    return d.weekday() < 5


def monsoon_intensity(d: date) -> float:
    """South-west monsoon over the Bay of Bengal, peaking in July and August."""
    peak = date(d.year, 7, 25)
    days = abs((d - peak).days)
    return math.exp(-((days / 55.0) ** 2))


def ou_walk(n: int, rng: random.Random, theta: float, sigma: float) -> list[float]:
    """Zero-mean Ornstein-Uhlenbeck path. Commodity factors revert; they do not
    wander off the way a free random walk does."""
    out: list[float] = []
    x = 0.0
    for _ in range(n):
        x += -theta * x + rng.gauss(0.0, sigma)
        out.append(x)
    return out


#: Persistent series-specific variation, as a share of the common factor's.
#:
#: Without it every series is a scaled copy of one latent factor, correlations
#: land at 0.99, and the projection model faces a likelihood ridge rather than a
#: peak: no optimiser converges because there is no unique optimum to find. Real
#: instruments share a cycle but keep their own story, and the model needs that
#: to have anything to estimate.
IDIO_THETA = 0.012

IDIO_SIGMA = {
    "proxy": 0.0115,
    "bunker": 0.0080,
    "commodity": 0.0105,
    "macro": 0.0022,
}


def build(days: int, seed: int, end: date) -> dict:
    rng = random.Random(seed)
    start = end - timedelta(days=days - 1)
    dates = [start + timedelta(days=i) for i in range(days)]

    # Two latent factors drive everything, which is why the exogenous
    # regressors in the projection model carry real signal rather than noise.
    demand = ou_walk(days, rng, theta=0.010, sigma=0.020)   # dry-bulk demand
    energy = ou_walk(days, rng, theta=0.008, sigma=0.016)   # crude and fuel complex

    series: dict[str, dict] = {}

    def add(metric: str, adapter: str, source: str, values: list) -> None:
        series[metric] = {
            "adapter": adapter,
            "source": source,
            "start": start.isoformat(),
            "freq": "D",
            "values": [None if v is None else round(v, 4) for v in values],
        }

    # ── Baltic CFD proxy and the owner equities ──────────────────────────────
    for metric, base in PROXY_BASE.items():
        beta = PROXY_BETA[metric]
        adapter = metric.split(".", 1)[0]
        label = "synthetic:yahoo:BDRY:scaled" if adapter == "baltic" else f"synthetic:yahoo:{metric.split('.')[1].upper()}"
        idio = ou_walk(days, rng, IDIO_THETA, IDIO_SIGMA["proxy"])
        vals = [
            base * math.exp(beta * demand[i] + idio[i] + rng.gauss(0, 0.006))
            if is_business_day(d) else None
            for i, d in enumerate(dates)
        ]
        add(metric, adapter, label, vals)

    # ── Bunkers track the energy factor ──────────────────────────────────────
    for metric, base in BUNKER_BASE.items():
        idio = ou_walk(days, rng, IDIO_THETA, IDIO_SIGMA["bunker"])
        vals = [
            base * math.exp(0.95 * energy[i] + idio[i] + rng.gauss(0, 0.005))
            if is_business_day(d) else None
            for i, d in enumerate(dates)
        ]
        add(metric, "bunker", "synthetic:manual:indicative", vals)

    # ── Commodities sit between the two factors ──────────────────────────────
    for metric, base in COMMODITY_BASE.items():
        w_demand = 0.55 if "iron_ore" in metric else 0.35
        w_energy = 0.30 if "iron_ore" in metric else 0.70
        idio = ou_walk(days, rng, IDIO_THETA, IDIO_SIGMA["commodity"])
        vals = [
            base * math.exp(w_demand * demand[i] + w_energy * energy[i] + idio[i] + rng.gauss(0, 0.006))
            if is_business_day(d) else None
            for i, d in enumerate(dates)
        ]
        add(metric, "commodity", "synthetic:yahoo:futures", vals)

    # ── Macro: the rupee drifts weaker, the Aussie tracks the demand factor ──
    for metric, base in MACRO_BASE.items():
        drift = 0.00007 if metric.endswith("usdinr") else 0.0
        beta = 0.0 if metric.endswith("usdinr") else 0.25
        idio = ou_walk(days, rng, IDIO_THETA, IDIO_SIGMA["macro"])
        vals = [
            base * math.exp(drift * i + beta * demand[i] + idio[i] + rng.gauss(0, 0.0018))
            if is_business_day(d) else None
            for i, d in enumerate(dates)
        ]
        add(metric, "macro", f"synthetic:fred:{metric.split('.')[1].upper()}", vals)

    # ── Congestion and AIS only need a recent window ─────────────────────────
    recent = max(0, days - 120)
    for port in DISCHARGE_PORTS:
        wait: list = [None] * days
        anchored: list = [None] * days
        base_wait = PORT_BASE_WAIT[port]
        base_anch = PORT_BASE_ANCHORED[port]
        for i in range(recent, days):
            m = monsoon_intensity(dates[i])
            # Berth queues lengthen in the monsoon as working hours are lost.
            wait[i] = max(0.2, base_wait * (1.0 + 0.45 * m) + rng.gauss(0, 0.35))
            anchored[i] = max(0, round(base_anch * (1.0 + 0.5 * m) + rng.gauss(0, 1.5)))
        add(f"congestion.{port}.wait_days", "congestion", "synthetic:manual:port-agent-report", wait)
        add(f"congestion.{port}.vessels_at_anchor", "congestion", "synthetic:manual:port-agent-report", anchored)

        # Weather covers a short window either side of today, as Open-Meteo does.
        precip: list = [None] * days
        wind: list = [None] * days
        stopped: list = [None] * days
        for i in range(max(0, days - 21), days):
            m = monsoon_intensity(dates[i])
            precip[i] = max(0.0, rng.gauss(1.5 + 17.0 * m, 3.0 + 9.0 * m))
            wind[i] = max(2.0, rng.gauss(13.0 + 14.0 * m, 4.0))
            stopped[i] = 1.0 if precip[i] >= 12.0 else 0.0
        add(f"weather.{port}.precip_mm", "weather", "synthetic:open-meteo", precip)
        add(f"weather.{port}.wind_kmh", "weather", "synthetic:open-meteo", wind)
        add(f"weather.{port}.work_stopped", "weather", "synthetic:derived", stopped)

    # AIS is a static dump, so it gets a single observation, not a series.
    ais_day = days - 1
    for corridor in CORRIDORS:
        vals: list = [None] * days
        vals[ais_day] = float(max(0, round(CORRIDOR_BASE_COUNT[corridor] + rng.gauss(0, 4))))
        add(f"ais.corridor.{corridor}.vessel_count", "ais", "synthetic:ais:static", vals)
    for cls, (p50, p90) in AIS_DRAFT.items():
        for suffix, value in (
            ("p50", p50), ("p90", p90), ("mean", (p50 * 2 + p90) / 3), ("count", float(AIS_HULLS[cls])),
        ):
            vals = [None] * days
            vals[ais_day] = value
            add(f"ais.draft.{cls}.{suffix}", "ais", "synthetic:ais:static", vals)

    return {
        "generated_at": end.isoformat(),
        "provenance": "synthetic-calibrated",
        "note": (
            "Levels and correlations are plausible but these are NOT market "
            "observations. Run scripts/refresh_snapshot.py on a networked "
            "machine to replace this with live data. freight.rate.* is not "
            "stored: it is derived from these proxies at bootstrap."
        ),
        "schema": "columnar-v1",
        "days": days,
        "seed": seed,
        "series": series,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=1095, help="calendar days of history")
    ap.add_argument("--seed", type=int, default=20260910)
    ap.add_argument("--end", type=str, default=None, help="last date, YYYY-MM-DD")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    end = date.fromisoformat(args.end) if args.end else date.today()
    payload = build(args.days, args.seed, end)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))

    points = sum(sum(1 for v in s["values"] if v is not None) for s in payload["series"].values())
    size_kb = args.out.stat().st_size / 1024
    print(f"wrote {args.out}")
    print(f"  series      {len(payload['series'])}")
    print(f"  observations {points:,}")
    print(f"  size        {size_kb:,.0f} KB")


if __name__ == "__main__":
    main()
