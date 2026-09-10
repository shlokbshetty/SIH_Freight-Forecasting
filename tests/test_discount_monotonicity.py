"""
Property-based tests for CVC Discount Monotonic Sensitivity.

Property 3: CVC Discount Monotonic Sensitivity
Validates: Requirements 1.3

For any cvc_discount_pct in [0.0, 15.0]:
  - Increasing discount_pct MUST monotonically decrease locked_cvc_rate
  - Sign of base_case_delta_inr changes predictably at break-even (not arbitrarily)

Fixed scenario:
  cargo_tonnage=75,000 MT
  num_voyages=4
  origin=NEWCASTLE, destination=HALDIA, vessel=PANAMAX

Run: pytest tests/test_discount_monotonicity.py -v
"""

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from engine.breakeven_analyzer import BreakEvenAnalyzer
from engine.financial_evaluator import FinancialEvaluator
from data.ports import get_port
from data.vessels import get_vessel_class
from data.mock_rates import OperationalCosts


# ─────────────────────────────────────────────────────────────────────────────
# Property 3: CVC Discount Monotonic Sensitivity
# ─────────────────────────────────────────────────────────────────────────────

def test_cvc_discount_monotonicity_full_range():
    """
    Property 3: Tests 100 cvc_discount_pct values uniformly sampled from [0.0, 15.0].
    Assert: As cvc_discount_pct increases, locked_cvc_rate strictly decreases.

    Fixed: cargo=75,000T, num_voyages=4, NEWCASTLE→HALDIA, PANAMAX
    """
    analyzer = BreakEvenAnalyzer()
    avg_spot_rate = 22.45  # Fixed reference spot rate

    # 100 values uniformly from 0.0 to 15.0
    n = 100
    discounts = [i * 15.0 / (n - 1) for i in range(n)]
    locked_rates = [analyzer.calculate_cvc_rate(avg_spot_rate, d) for d in discounts]

    for i in range(len(locked_rates) - 1):
        # Strictly non-increasing (allow equal for identical discount values)
        assert locked_rates[i] >= locked_rates[i + 1], (
            f"Monotonicity violated: discount={discounts[i]:.3f}% → rate={locked_rates[i]:.4f}, "
            f"discount={discounts[i+1]:.3f}% → rate={locked_rates[i+1]:.4f}"
        )


def test_cvc_discount_zero_matches_spot_rate():
    """At 0% discount, locked_cvc_rate must equal average_spot_rate."""
    analyzer = BreakEvenAnalyzer()
    spot = 22.45
    locked = analyzer.calculate_cvc_rate(spot, 0.0)
    assert locked == round(spot, 2), f"0% discount: expected {spot}, got {locked}"


def test_cvc_discount_15pct_reduces_rate():
    """At 15% discount, locked rate = spot × 0.85."""
    analyzer = BreakEvenAnalyzer()
    spot = 22.45
    locked = analyzer.calculate_cvc_rate(spot, 15.0)
    expected = round(spot * 0.85, 2)
    assert locked == expected, f"15% discount: expected {expected}, got {locked}"


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
@given(
    discount_a=st.floats(min_value=0.0, max_value=14.9, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=0.01, max_value=0.5, allow_nan=False, allow_infinity=False),
    avg_spot=st.floats(min_value=5.0, max_value=80.0, allow_nan=False, allow_infinity=False),
)
def test_discount_monotonicity_property(discount_a: float, delta: float, avg_spot: float):
    """
    Property: For any (discount_a, discount_b = discount_a + delta) pair where both
    are in [0, 15], the CVC rate at discount_a >= rate at discount_b.
    """
    discount_b = min(15.0, discount_a + delta)
    analyzer = BreakEvenAnalyzer()

    rate_a = analyzer.calculate_cvc_rate(avg_spot, discount_a)
    rate_b = analyzer.calculate_cvc_rate(avg_spot, discount_b)

    assert rate_a >= rate_b, (
        f"Monotonicity violated: discount_a={discount_a:.3f}% → {rate_a:.4f}, "
        f"discount_b={discount_b:.3f}% → {rate_b:.4f} (spot={avg_spot:.2f})"
    )


def test_evaluator_discount_monotonicity_delta_sign():
    """
    For fixed NEWCASTLE→HALDIA Panamax 75K 4 voyages:
    As CVC discount increases from 0% to 15%, is_cvc_favorable should become
    True at some threshold and stay True (CVC gets cheaper relative to spot).
    Tests 100 discount values and verifies sign consistency.
    """
    evaluator = FinancialEvaluator()
    origin = get_port("NEWCASTLE")
    destination = get_port("HALDIA")
    vessel = get_vessel_class("PANAMAX")
    cargo = 75_000.0
    num_voyages = 4

    n = 100
    discounts = [i * 15.0 / (n - 1) for i in range(n)]
    results = []

    for d in discounts:
        r = evaluator.evaluate(
            cargo_tonnage=cargo,
            origin=origin,
            destination=destination,
            vessel=vessel,
            num_voyages=num_voyages,
            cvc_discount_pct=d,
        )
        results.append(r)

    # Locked CVC rate must strictly decrease as discount increases
    locked_rates = [r.locked_cvc_rate for r in results]
    for i in range(len(locked_rates) - 1):
        assert locked_rates[i] >= locked_rates[i + 1], (
            f"locked_cvc_rate not monotonically decreasing at discount index {i}: "
            f"{locked_rates[i]:.4f} → {locked_rates[i+1]:.4f}"
        )

    # Once cvc becomes favorable it should stay favorable as discount grows
    # Find first favorable discount
    favorable_indices = [i for i, r in enumerate(results) if r.is_cvc_favorable]
    if favorable_indices:
        first_favorable = favorable_indices[0]
        # All results after the first favorable must also be favorable
        # (higher discount = lower CVC rate = CVC always wins)
        for i in range(first_favorable, len(results)):
            assert results[i].is_cvc_favorable, (
                f"CVC favorable reversed at discount={discounts[i]:.2f}% "
                f"after being favorable at discount={discounts[first_favorable]:.2f}%"
            )
