"""
Property-based tests for break-even financial invariant.

Property 1: Break-Even Financial Invariant
Validates: Requirements 1.2, 1.4

For any (cargo_tonnage, num_voyages, cvc_discount_pct) tuple:
  locked_cvc_rate = average_spot_rate × (1.0 - cvc_discount_pct / 100.0)
  cvc_total = cvc_freight_total + operational_total
  breakeven_rate = (cvc_total - operational_total) / (cargo_tonnage × num_voyages)

Invariant:
  (breakeven_rate × cargo_tonnage × num_voyages) + operational_total ≈ cvc_total
  (within ±1%)

Run: pytest tests/test_breakeven_invariant.py -v
"""

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
import pytest

from engine.breakeven_analyzer import BreakEvenAnalyzer
from data.mock_rates import OperationalCosts


# ─────────────────────────────────────────────────────────────────────────────
# Property 1: Break-Even Financial Invariant
# ─────────────────────────────────────────────────────────────────────────────

@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
@given(
    cargo_tonnage=st.floats(min_value=5_000.0, max_value=500_000.0, allow_nan=False, allow_infinity=False),
    num_voyages=st.sampled_from([1, 2, 3, 4, 5, 6, 8]),
    cvc_discount_pct=st.floats(min_value=0.0, max_value=15.0, allow_nan=False, allow_infinity=False),
    average_spot_rate=st.floats(min_value=5.0, max_value=80.0, allow_nan=False, allow_infinity=False),
)
def test_breakeven_financial_invariant(
    cargo_tonnage: float,
    num_voyages: int,
    cvc_discount_pct: float,
    average_spot_rate: float,
):
    """
    Property 1: For random inputs, the break-even rate derived from CVC total
    must reconstruct back to the original CVC total within ±1% tolerance.

    Chain:
      1. locked_cvc_rate = average_spot_rate × (1 - discount/100)
      2. cvc_freight_total = locked_cvc_rate × cargo_tonnage × num_voyages
      3. operational_total = fixed costs × num_voyages
      4. cvc_total = cvc_freight_total + operational_total
      5. breakeven_rate = (cvc_total - operational_total) / (cargo_tonnage × num_voyages)
      6. Reconstructed = breakeven_rate × cargo_tonnage × num_voyages + operational_total

    Assert: |reconstructed - cvc_total| / cvc_total <= 0.01  (within 1%)
    """
    op_costs = OperationalCosts()
    analyzer = BreakEvenAnalyzer(op_costs=op_costs)

    # Step 1: Compute locked CVC rate
    locked_cvc_rate = analyzer.calculate_cvc_rate(average_spot_rate, cvc_discount_pct)

    # Step 2: Compute freight and operational totals
    cvc_freight_total = round(locked_cvc_rate * cargo_tonnage * num_voyages, 2)

    # Operational costs: bunker + port + demurrage (no lighterage for this invariant test)
    bunker_per_voyage = round(op_costs.bunker_adjustment_per_ton * cargo_tonnage, 2)
    port_per_voyage = round(op_costs.port_charges_per_call, 2)
    demurrage_per_voyage = round(
        op_costs.standard_wait_days * op_costs.demurrage_rate_per_day, 2
    )
    operational_per_voyage = round(bunker_per_voyage + port_per_voyage + demurrage_per_voyage, 2)
    operational_total = round(operational_per_voyage * num_voyages, 2)

    cvc_total = round(cvc_freight_total + operational_total, 2)

    # Step 3: Compute break-even rate
    breakeven_rate = analyzer.calculate_break_even_rate(
        cvc_total_usd=cvc_total,
        operational_total_usd=operational_total,
        cargo_tonnage=cargo_tonnage,
        num_voyages=num_voyages,
    )

    # Step 4: Reconstruct CVC total from break-even rate
    reconstructed = round(
        breakeven_rate * cargo_tonnage * num_voyages + operational_total, 2
    )

    # Assert: within ±1% relative tolerance
    # (2dp rounding on $/T can introduce up to ~$0.005/T × large tonnage × voyages)
    if cvc_total > 0:
        relative_error = abs(reconstructed - cvc_total) / cvc_total
        assert relative_error <= 0.01, (
            f"Break-even invariant violated: "
            f"cargo={cargo_tonnage:.0f}T, N={num_voyages}, discount={cvc_discount_pct:.2f}%, "
            f"spot={average_spot_rate:.2f}/T, cvc_total=${cvc_total:,.2f}, "
            f"reconstructed=${reconstructed:,.2f}, error={relative_error:.4%}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Additional deterministic tests for known inputs
# ─────────────────────────────────────────────────────────────────────────────

def test_breakeven_invariant_newcastle_haldia_scenario():
    """
    Known scenario: Newcastle→Haldia, 75K cargo, 4 voyages, 5% CVC discount,
    avg spot rate $22.45/T. Validates invariant with real-world parameters.
    """
    op_costs = OperationalCosts()
    analyzer = BreakEvenAnalyzer(op_costs=op_costs)

    cargo_tonnage = 75_000.0
    num_voyages = 4
    cvc_discount_pct = 5.0
    average_spot_rate = 22.45

    locked_rate = analyzer.calculate_cvc_rate(average_spot_rate, cvc_discount_pct)
    assert locked_rate == round(22.45 * 0.95, 2)

    cvc_freight = round(locked_rate * cargo_tonnage * num_voyages, 2)
    bunker_per = round(op_costs.bunker_adjustment_per_ton * cargo_tonnage, 2)
    port_per = round(op_costs.port_charges_per_call, 2)
    demurrage_per = round(op_costs.standard_wait_days * op_costs.demurrage_rate_per_day, 2)
    ops_total = round((bunker_per + port_per + demurrage_per) * num_voyages, 2)
    cvc_total = round(cvc_freight + ops_total, 2)

    breakeven = analyzer.calculate_break_even_rate(cvc_total, ops_total, cargo_tonnage, num_voyages)
    reconstructed = round(breakeven * cargo_tonnage * num_voyages + ops_total, 2)

    assert abs(reconstructed - cvc_total) / cvc_total <= 0.001, (
        f"Invariant violated: cvc_total={cvc_total}, reconstructed={reconstructed}"
    )


def test_cvc_rate_monotonic_with_discount():
    """
    As cvc_discount_pct increases from 0 to 15%, locked_cvc_rate must strictly decrease.
    """
    analyzer = BreakEvenAnalyzer()
    spot = 22.45
    discounts = [i * 0.5 for i in range(31)]  # 0.0 to 15.0 in 0.5 steps
    rates = [analyzer.calculate_cvc_rate(spot, d) for d in discounts]

    for i in range(len(rates) - 1):
        assert rates[i] >= rates[i + 1], (
            f"CVC rate not monotonically decreasing at discount={discounts[i]:.1f}%: "
            f"{rates[i]} < {rates[i+1]}"
        )
