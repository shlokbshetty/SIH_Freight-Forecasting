"""Turning the projection into the rate curve the commercial endpoints need.

/api/match and /api/contract both want the same thing: today's rate, and the
projected rate with its uncertainty at some number of days out. This is the one
place that asks the model for it, so the two endpoints cannot drift apart.
"""

from __future__ import annotations

import logging
import math

from models import project

log = logging.getLogger(__name__)

#: The published band is 80%, whose half-width is this many standard deviations.
P80_Z = 1.2816


class RateCurve:
    """Projected rate and standard deviation by day offset from today."""

    def __init__(self, market_rate: float, means: list[float], sds: list[float], source: str):
        self.market_rate = market_rate
        self._means = means
        self._sds = sds
        self.source = source

    def at(self, day_offset: int) -> tuple[float, float]:
        if not self._means:
            return self.market_rate, 0.0
        idx = max(0, min(len(self._means) - 1, int(day_offset) - 1))
        return self._means[idx], self._sds[idx]

    def mean_at(self, day_offset: int) -> float:
        return self.at(day_offset)[0]


def _flat_curve(market_rate: float, daily_sd: float, steps: int, source: str) -> RateCurve:
    """Random walk from today's level. Used when no model is loaded."""
    means = [market_rate] * steps
    sds = [market_rate * daily_sd * math.sqrt(i + 1) for i in range(steps)]
    return RateCurve(market_rate, means, sds, source)


def build_rate_curve(state, vessel_class: str, steps: int = 400) -> RateCurve:
    """Never raises. Degrades from fitted model, to random walk, to flat."""
    vessel_class = vessel_class.lower()

    try:
        frame = project.build_feature_frame(state.conn, vessel_class)
    except Exception as exc:  # noqa: BLE001
        log.warning("no feature frame for %s: %s", vessel_class, exc)
        from data import cache

        row = cache.latest_observation(state.conn, f"freight.rate.{vessel_class}")
        market = float(row["value"]) if row else 0.0
        return _flat_curve(market, 0.012, steps, "last-observation")

    market_rate = float(frame["rate"].iloc[-1])
    daily_sd = float(frame["log_rate"].diff().dropna().std() or 0.012)

    bundle = state.model_for(vessel_class)
    if bundle is None:
        return _flat_curve(market_rate, daily_sd, steps, "random-walk")

    try:
        horizon = min(steps, max(project.HORIZONS))
        result = project.forecast(bundle, frame, horizons=(horizon,))
        means = [float(p["value"]) for p in result["forecast"]]
        # Recover the standard deviation from the 80% band half-width.
        sds = [
            max(0.0, (float(b["upper"]) - float(b["lower"])) / (2 * P80_Z))
            for b in result["intervals"]["p80"]
        ]
        # A programme can run past the model's horizon. Extend the last level
        # and keep widening the band with the square root of time.
        while len(means) < steps:
            means.append(means[-1])
            sds.append(sds[-1] * math.sqrt((len(sds) + 1) / len(sds)))
        return RateCurve(market_rate, means, sds, "sarimax")
    except Exception as exc:  # noqa: BLE001
        log.warning("projection unavailable for %s (%s); using a random walk", vessel_class, exc)
        return _flat_curve(market_rate, daily_sd, steps, "random-walk")
