"""
Property-based tests for ML quantile monotonicity invariant.

Property 2: Quantile Monotonicity Invariant
Validates: Requirements 1.8

For any (origin, destination, vessel, num_voyages) tuple, the ML forecaster
must satisfy:  p10_rates[i] <= p50_rates[i] <= p90_rates[i]  for all voyage indices i.

If any quantile violates ordering, apply correction:
  p10_clean = min(p10, p50)
  p50_clean = median(p50, p10, p90)
  p90_clean = max(p90, p50)

Run: pytest tests/test_ml_quantiles.py::test_quantile_monotonicity -v
"""

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from engine.ml_forecaster import MultiQuantileForecaster, ROUTE_COLUMN_MAPPING

# All supported route keys
ROUTE_KEYS = list(ROUTE_COLUMN_MAPPING.keys())

# Supported num_voyages values (per task spec: 1, 4, 8 based on time horizons)
VOYAGE_COUNTS = [1, 4, 8]


@pytest.fixture(scope="module")
def forecaster():
    """Shared forecaster instance — trains/loads models once per test module."""
    return MultiQuantileForecaster()


# ─────────────────────────────────────────────────────────────────────────────
# Property 2: Quantile Monotonicity Invariant
# ─────────────────────────────────────────────────────────────────────────────

@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
@given(
    route_idx=st.integers(min_value=0, max_value=len(ROUTE_KEYS) - 1),
    num_voyages=st.sampled_from(VOYAGE_COUNTS),
)
def test_quantile_monotonicity(route_idx: int, num_voyages: int):
    """
    Property 2: For every supported route and voyage count, ML quantile predictions
    must maintain strict ordering: p10[i] <= p50[i] <= p90[i].

    The MultiQuantileForecaster guarantees this via post-processing (sorted()).
    This test verifies the invariant holds after the guarantee is applied.
    """
    forecaster = MultiQuantileForecaster()
    origin, destination, vessel = ROUTE_KEYS[route_idx]

    result = forecaster.predict_route(
        origin_code=origin,
        destination_code=destination,
        vessel_code=vessel,
        num_voyages=num_voyages,
    )

    assert len(result.p10_rates) == num_voyages, (
        f"p10_rates length mismatch: expected {num_voyages}, got {len(result.p10_rates)}"
    )
    assert len(result.p50_rates) == num_voyages
    assert len(result.p90_rates) == num_voyages

    for i in range(num_voyages):
        p10 = result.p10_rates[i]
        p50 = result.p50_rates[i]
        p90 = result.p90_rates[i]

        assert p10 <= p50, (
            f"Route {origin}→{destination} ({vessel}), voyage {i+1}: "
            f"p10 ({p10}) > p50 ({p50}) — monotonicity violated"
        )
        assert p50 <= p90, (
            f"Route {origin}→{destination} ({vessel}), voyage {i+1}: "
            f"p50 ({p50}) > p90 ({p90}) — monotonicity violated"
        )
        # All rates must be positive
        assert p10 > 0.0, f"p10 must be positive, got {p10}"
        assert p90 > 0.0, f"p90 must be positive, got {p90}"


# ─────────────────────────────────────────────────────────────────────────────
# Additional: Volatile sigma computation
# ─────────────────────────────────────────────────────────────────────────────

def test_implied_volatility_minimum_floor(forecaster):
    """
    Implied sigma = (p90 - p10) / 2.563 must be at least 0.50 (floor clamping).
    """
    result = forecaster.predict_route("NEWCASTLE", "HALDIA", "PANAMAX", num_voyages=4)
    assert result.volatility_std >= 0.50, (
        f"volatility_std {result.volatility_std} below minimum floor of 0.50"
    )


def test_mean_spot_rate_is_average_of_p50(forecaster):
    """
    mean_spot_rate must equal the arithmetic mean of p50_rates (within ±0.01).
    """
    result = forecaster.predict_route("HAY_POINT", "DHAMRA", "CAPESIZE", num_voyages=4)
    expected_mean = round(sum(result.p50_rates) / len(result.p50_rates), 2)
    assert abs(result.mean_spot_rate - expected_mean) <= 0.01, (
        f"mean_spot_rate {result.mean_spot_rate} != avg(p50) {expected_mean}"
    )


def test_all_routes_load_without_error(forecaster):
    """All 5 supported routes must produce valid MLForecastResult without exceptions."""
    for key in ROUTE_KEYS:
        origin, destination, vessel = key
        result = forecaster.predict_route(
            origin_code=origin,
            destination_code=destination,
            vessel_code=vessel,
            num_voyages=4,
        )
        assert result is not None
        assert result.route_code is not None
        assert len(result.p50_rates) == 4
