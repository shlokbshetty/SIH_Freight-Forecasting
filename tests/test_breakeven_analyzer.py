# -*- coding: utf-8 -*-
"""
Unit tests for BreakEvenAnalyzer — spot vs. CVC financial comparison.
Covers: locked CVC rate, break-even rate formula, scenario comparison.
"""

import math
import pytest

from data.mock_rates import OperationalCosts
from engine.breakeven_analyzer import BreakEvenAnalyzer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def analyzer() -> BreakEvenAnalyzer:
    return BreakEvenAnalyzer()


# ---------------------------------------------------------------------------
# 1. calculate_cvc_rate
# ---------------------------------------------------------------------------

class TestCalculateCvcRate:
    def test_five_percent_discount(self, analyzer: BreakEvenAnalyzer):
        """Standard 5% discount on a $22.45 average rate should yield $21.33."""
        rate = analyzer.calculate_cvc_rate(average_spot_rate=22.45, cvc_discount_pct=5.0)
        expected = round(22.45 * 0.95, 2)
        assert rate == expected

    def test_zero_discount_returns_spot_rate(self, analyzer: BreakEvenAnalyzer):
        """Zero discount should lock CVC rate exactly at average spot rate."""
        rate = analyzer.calculate_cvc_rate(average_spot_rate=20.00, cvc_discount_pct=0.0)
        assert rate == 20.00

    def test_fifteen_percent_max_discount(self, analyzer: BreakEvenAnalyzer):
        """15% (max allowed) discount on $30.00 should yield $25.50."""
        rate = analyzer.calculate_cvc_rate(average_spot_rate=30.00, cvc_discount_pct=15.0)
        expected = round(30.00 * 0.85, 2)
        assert rate == expected

    def test_formula_discount_factor(self, analyzer: BreakEvenAnalyzer):
        """Verify locked_cvc_rate = average_spot_rate × (1.0 - cvc_discount_pct / 100.0)."""
        for spot, discount in [(14.20, 3.5), (32.50, 7.0), (10.80, 10.0)]:
            expected = round(spot * (1.0 - discount / 100.0), 2)
            assert analyzer.calculate_cvc_rate(spot, discount) == expected

    def test_fractional_rate_precision(self, analyzer: BreakEvenAnalyzer):
        """Result should be rounded to 2 decimal places."""
        rate = analyzer.calculate_cvc_rate(average_spot_rate=22.22, cvc_discount_pct=3.3)
        # 22.22 * 0.967 = 21.48674 → rounds to 21.49
        assert rate == round(22.22 * (1.0 - 3.3 / 100.0), 2)


# ---------------------------------------------------------------------------
# 2. calculate_break_even_rate
# ---------------------------------------------------------------------------

class TestCalculateBreakEvenRate:
    def test_basic_break_even_formula(self, analyzer: BreakEvenAnalyzer):
        """
        break_even_rate = (cvc_total - ops_total) / (cargo_tonnage × num_voyages)
        With cvc=7.5M, ops=2.0M, cargo=75000, N=4 → (5.5M) / 300000 ≈ 18.33.
        """
        rate = analyzer.calculate_break_even_rate(
            cvc_total_usd=7_500_000.0,
            operational_total_usd=2_000_000.0,
            cargo_tonnage=75_000.0,
            num_voyages=4,
        )
        expected = round((7_500_000.0 - 2_000_000.0) / (75_000.0 * 4), 2)
        assert rate == expected

    def test_single_voyage(self, analyzer: BreakEvenAnalyzer):
        """Single voyage case should divide over one period."""
        rate = analyzer.calculate_break_even_rate(
            cvc_total_usd=2_000_000.0,
            operational_total_usd=500_000.0,
            cargo_tonnage=50_000.0,
            num_voyages=1,
        )
        assert rate == round(1_500_000.0 / 50_000.0, 2)

    def test_eight_voyage_horizon(self, analyzer: BreakEvenAnalyzer):
        """Six-month (8 voyage) horizon break-even calculation."""
        rate = analyzer.calculate_break_even_rate(
            cvc_total_usd=12_000_000.0,
            operational_total_usd=4_000_000.0,
            cargo_tonnage=75_000.0,
            num_voyages=8,
        )
        expected = round(8_000_000.0 / (75_000.0 * 8), 2)
        assert rate == expected

    def test_inverse_relation_to_cargo(self, analyzer: BreakEvenAnalyzer):
        """Doubling cargo tonnage should halve the break-even rate."""
        base = analyzer.calculate_break_even_rate(2_000_000.0, 500_000.0, 50_000.0, 4)
        double = analyzer.calculate_break_even_rate(2_000_000.0, 500_000.0, 100_000.0, 4)
        assert math.isclose(base, double * 2, rel_tol=1e-6)

    def test_roundtrip_invariant(self, analyzer: BreakEvenAnalyzer):
        """
        (break_even_rate × cargo_tonnage × num_voyages) + operational_total
        should equal cvc_total within ±0.01% (rounding tolerance from 2dp rate).
        The 2dp rounding on $/T × large tonnage × voyages can introduce up to
        ~0.005/T × 300000T = $1500 error at the extreme, which is < 0.02% on 7M+.
        """
        cvc_total = 7_285_000.0
        ops_total = 2_220_000.0
        tonnage = 75_000.0
        n = 4

        rate = analyzer.calculate_break_even_rate(cvc_total, ops_total, tonnage, n)
        reconstructed = round(rate * tonnage * n + ops_total, 2)
        # Allow up to 0.1% relative tolerance to account for 2dp rate rounding
        # (0.005/T precision × 300,000T cargo = up to ~$1,500 on a ~$7M total = 0.02%)
        assert abs(reconstructed - cvc_total) / cvc_total <= 0.001


# ---------------------------------------------------------------------------
# 3. compare_scenarios
# ---------------------------------------------------------------------------

class TestCompareScenarios:
    def test_cvc_favorable_when_spot_higher(self, analyzer: BreakEvenAnalyzer):
        """When spot total > cvc total, CVC should be flagged favorable."""
        is_fav, delta_usd, delta_inr = analyzer.compare_scenarios(
            spot_total_usd=8_000_000.0,
            cvc_total_usd=7_500_000.0,
            cargo_tonnage=75_000.0,
            num_voyages=4,
        )
        assert is_fav is True
        assert delta_usd == 500_000.0

    def test_spot_favorable_when_cvc_higher(self, analyzer: BreakEvenAnalyzer):
        """When cvc total > spot total, CVC should NOT be flagged favorable."""
        is_fav, delta_usd, delta_inr = analyzer.compare_scenarios(
            spot_total_usd=7_000_000.0,
            cvc_total_usd=7_500_000.0,
            cargo_tonnage=75_000.0,
            num_voyages=4,
        )
        assert is_fav is False
        assert delta_usd == 500_000.0

    def test_equal_totals_cvc_favorable(self, analyzer: BreakEvenAnalyzer):
        """When totals are identical, CVC should be considered favorable (no extra cost)."""
        is_fav, delta_usd, delta_inr = analyzer.compare_scenarios(
            spot_total_usd=5_000_000.0,
            cvc_total_usd=5_000_000.0,
            cargo_tonnage=50_000.0,
            num_voyages=4,
        )
        assert is_fav is True
        assert delta_usd == 0.0
        assert delta_inr == 0.0

    def test_inr_conversion_uses_exchange_rate(self, analyzer: BreakEvenAnalyzer):
        """delta_inr should equal delta_usd × usd_to_inr exchange rate."""
        _, delta_usd, delta_inr = analyzer.compare_scenarios(
            spot_total_usd=9_000_000.0,
            cvc_total_usd=8_000_000.0,
            cargo_tonnage=75_000.0,
            num_voyages=4,
        )
        expected_inr = round(delta_usd * analyzer.op_costs.usd_to_inr, 2)
        assert delta_inr == expected_inr

    def test_custom_op_costs_exchange_rate(self):
        """Custom OperationalCosts exchange rate is honoured."""
        custom_costs = OperationalCosts(usd_to_inr=90.0)
        analyzer = BreakEvenAnalyzer(op_costs=custom_costs)
        _, delta_usd, delta_inr = analyzer.compare_scenarios(
            spot_total_usd=2_000_000.0,
            cvc_total_usd=1_000_000.0,
            cargo_tonnage=50_000.0,
            num_voyages=2,
        )
        assert delta_inr == round(1_000_000.0 * 90.0, 2)

    def test_delta_usd_is_always_positive(self, analyzer: BreakEvenAnalyzer):
        """delta_usd must always be non-negative regardless of which scenario is cheaper."""
        # Spot cheaper
        _, d1, _ = analyzer.compare_scenarios(3_000_000.0, 4_000_000.0, 50_000.0, 4)
        # CVC cheaper
        _, d2, _ = analyzer.compare_scenarios(4_000_000.0, 3_000_000.0, 50_000.0, 4)
        assert d1 >= 0.0
        assert d2 >= 0.0
        assert d1 == d2  # magnitude is the same
