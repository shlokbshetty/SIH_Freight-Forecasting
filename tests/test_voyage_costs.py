"""
Unit tests for VoyageCostBreakdown data model and VoyageCostCalculator class.

Validates:
  - VoyageCostBreakdown dataclass field presence and types
  - VoyageCostCalculator.calculate_voyage_costs() per-voyage formula
  - voyage_total = freight_cost + bunker_adj + port_charges + (wait_days × demurrage) + lighterage
  - Correct number of breakdowns returned
  - Edge cases: lighterage, custom wait days, zero lighterage

Requirements: 1.1
"""

import pytest
from engine.data_models import VoyageCostBreakdown
from engine.voyage_cost import VoyageCostCalculator
from data.mock_rates import OperationalCosts


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_calculator(
    bunker=1.80,
    port_charges=35000.0,
    demurrage_per_day=18000.0,
    standard_wait_days=1.5,
    lighterage_rate=6.50,
    lighterage_penalty_days=3.5,
) -> VoyageCostCalculator:
    op = OperationalCosts(
        bunker_adjustment_per_ton=bunker,
        port_charges_per_call=port_charges,
        demurrage_rate_per_day=demurrage_per_day,
        standard_wait_days=standard_wait_days,
        lighterage_rate_per_ton=lighterage_rate,
        lighterage_time_penalty_days=lighterage_penalty_days,
    )
    return VoyageCostCalculator(op_costs=op)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Data Model Structure
# ─────────────────────────────────────────────────────────────────────────────

class TestVoyageCostBreakdownModel:
    """Verifies VoyageCostBreakdown dataclass has all required fields."""

    def test_required_fields_present(self):
        """All 17 required fields must be constructable."""
        vb = VoyageCostBreakdown(
            voyage_number=1,
            spot_freight_rate=22.50,
            spot_freight_cost=1_687_500.0,
            cvc_freight_rate=21.375,
            cvc_freight_cost=1_603_125.0,
            bunker_adj_cost=135_000.0,
            port_charges=35_000.0,
            wait_days=1.5,
            demurrage_cost=27_000.0,
            lighterage_tonnage=0.0,
            lighterage_cost=0.0,
            spot_voyage_total=1_884_500.0,
            cvc_voyage_total=1_800_125.0,
            voyage_savings=84_375.0,
            p10_spot_rate=21.375,
            p90_spot_rate=24.30,
        )
        assert vb.voyage_number == 1
        assert vb.spot_freight_rate == 22.50
        assert vb.cvc_freight_rate == 21.375
        assert vb.lighterage_tonnage == 0.0
        assert vb.p10_spot_rate == 21.375
        assert vb.p90_spot_rate == 24.30

    def test_optional_fields_default_to_zero(self):
        """p10_spot_rate and p90_spot_rate default to 0.0."""
        vb = VoyageCostBreakdown(
            voyage_number=1,
            spot_freight_rate=20.0,
            spot_freight_cost=1_500_000.0,
            cvc_freight_rate=19.0,
            cvc_freight_cost=1_425_000.0,
            bunker_adj_cost=112_500.0,
            port_charges=35_000.0,
            wait_days=1.5,
            demurrage_cost=27_000.0,
            lighterage_tonnage=0.0,
            lighterage_cost=0.0,
            spot_voyage_total=1_674_500.0,
            cvc_voyage_total=1_599_500.0,
            voyage_savings=75_000.0,
        )
        assert vb.p10_spot_rate == 0.0
        assert vb.p90_spot_rate == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 2. VoyageCostCalculator — Core Formula Verification
# ─────────────────────────────────────────────────────────────────────────────

class TestVoyageCostCalculatorFormula:
    """Verifies voyage_total = freight_cost + bunker_adj + port_charges + demurrage + lighterage."""

    def test_single_voyage_no_lighterage(self):
        """
        cargo=75,000T, spot_rate=22.50, cvc_rate=21.375 (5% discount),
        bunker=1.80/T → $135,000, port=$35,000, wait=1.5d, demurrage=1.5×18000=$27,000.
        Expected spot_voyage_total = 1,687,500 + 135,000 + 35,000 + 27,000 = 1,884,500
        """
        calc = _make_calculator()
        breakdowns = calc.calculate_voyage_costs(
            cargo_tonnage=75_000.0,
            num_voyages=1,
            spot_rates=[22.50],
            cvc_rate=21.375,
        )

        assert len(breakdowns) == 1
        v = breakdowns[0]

        expected_spot_freight = round(22.50 * 75_000.0, 2)
        expected_bunker = round(1.80 * 75_000.0, 2)
        expected_demurrage = round(1.5 * 18_000.0, 2)
        expected_total = round(expected_spot_freight + expected_bunker + 35_000.0 + expected_demurrage, 2)

        assert v.spot_freight_cost == expected_spot_freight
        assert v.bunker_adj_cost == expected_bunker
        assert v.port_charges == 35_000.0
        assert v.demurrage_cost == expected_demurrage
        assert v.lighterage_cost == 0.0
        assert v.spot_voyage_total == expected_total

    def test_voyage_total_formula_invariant(self):
        """
        spot_voyage_total must equal spot_freight_cost + bunker_adj_cost
        + port_charges + demurrage_cost + lighterage_cost for every voyage.
        """
        calc = _make_calculator()
        spot_rates = [22.50, 23.10, 21.80, 22.40]
        breakdowns = calc.calculate_voyage_costs(
            cargo_tonnage=75_000.0,
            num_voyages=4,
            spot_rates=spot_rates,
            cvc_rate=21.375,
        )
        for v in breakdowns:
            expected = round(
                v.spot_freight_cost + v.bunker_adj_cost + v.port_charges
                + v.demurrage_cost + v.lighterage_cost,
                2,
            )
            assert v.spot_voyage_total == expected, (
                f"Voyage {v.voyage_number}: {v.spot_voyage_total} != {expected}"
            )

    def test_cvc_voyage_total_formula_invariant(self):
        """
        cvc_voyage_total must equal cvc_freight_cost + bunker_adj_cost
        + port_charges + demurrage_cost + lighterage_cost for every voyage.
        """
        calc = _make_calculator()
        spot_rates = [22.50, 23.10, 21.80, 22.40]
        breakdowns = calc.calculate_voyage_costs(
            cargo_tonnage=75_000.0,
            num_voyages=4,
            spot_rates=spot_rates,
            cvc_rate=20.0,
        )
        for v in breakdowns:
            expected = round(
                v.cvc_freight_cost + v.bunker_adj_cost + v.port_charges
                + v.demurrage_cost + v.lighterage_cost,
                2,
            )
            assert v.cvc_voyage_total == expected, (
                f"Voyage {v.voyage_number}: {v.cvc_voyage_total} != {expected}"
            )

    def test_voyage_savings_is_difference(self):
        """voyage_savings = spot_voyage_total - cvc_voyage_total."""
        calc = _make_calculator()
        breakdowns = calc.calculate_voyage_costs(
            cargo_tonnage=75_000.0,
            num_voyages=4,
            spot_rates=[22.50, 23.10, 21.80, 22.40],
            cvc_rate=21.0,
        )
        for v in breakdowns:
            assert v.voyage_savings == round(v.spot_voyage_total - v.cvc_voyage_total, 2)

    def test_voyage_numbers_sequential(self):
        """voyage_number must be 1, 2, 3, ... N."""
        calc = _make_calculator()
        breakdowns = calc.calculate_voyage_costs(
            cargo_tonnage=75_000.0,
            num_voyages=4,
            spot_rates=[22.50, 23.10, 21.80, 22.40],
            cvc_rate=21.375,
        )
        assert [v.voyage_number for v in breakdowns] == [1, 2, 3, 4]


# ─────────────────────────────────────────────────────────────────────────────
# 3. VoyageCostCalculator — Lighterage Scenario
# ─────────────────────────────────────────────────────────────────────────────

class TestVoyageCostCalculatorLighterage:
    """Verifies lighterage costs are included in voyage totals."""

    def test_lighterage_included_in_voyage_total(self):
        """
        When lighterage_cost_per_voyage > 0, it must appear in spot/cvc voyage totals.
        Scenario: 31,034T lightered at $6.50/T → $201,721 lighterage cost.
        """
        lightered_tonnage = 31_034.0
        lighterage_cost = round(lightered_tonnage * 6.50, 2)  # 201,721.00

        calc = _make_calculator()
        breakdowns = calc.calculate_voyage_costs(
            cargo_tonnage=75_000.0,
            num_voyages=1,
            spot_rates=[22.50],
            cvc_rate=21.375,
            lighterage_tonnage=lightered_tonnage,
            lighterage_cost_per_voyage=lighterage_cost,
        )
        v = breakdowns[0]

        assert v.lighterage_tonnage == lightered_tonnage
        assert v.lighterage_cost == lighterage_cost

        # Voyage total must include lighterage
        expected_total = round(
            v.spot_freight_cost + v.bunker_adj_cost + v.port_charges
            + v.demurrage_cost + lighterage_cost,
            2,
        )
        assert v.spot_voyage_total == expected_total

    def test_lighterage_wait_days_override(self):
        """
        wait_days_override=5.0 (1.5 standard + 3.5 lighterage penalty) must
        produce demurrage = 5.0 × 18,000 = $90,000.
        """
        calc = _make_calculator()
        breakdowns = calc.calculate_voyage_costs(
            cargo_tonnage=75_000.0,
            num_voyages=1,
            spot_rates=[22.50],
            cvc_rate=21.375,
            wait_days_override=5.0,
        )
        v = breakdowns[0]
        assert v.wait_days == 5.0
        assert v.demurrage_cost == round(5.0 * 18_000.0, 2)


# ─────────────────────────────────────────────────────────────────────────────
# 4. VoyageCostCalculator — CVC vs Spot Relationship
# ─────────────────────────────────────────────────────────────────────────────

class TestCVCvsSpotRelationship:
    """Verifies CVC rate produces lower total when discount is applied."""

    def test_5pct_cvc_discount_saves_money(self):
        """With 5% CVC discount, cvc_voyage_total < spot_voyage_total."""
        calc = _make_calculator()
        avg_spot = 22.45
        cvc_rate = round(avg_spot * (1.0 - 5.0 / 100.0), 2)  # 21.3275

        breakdowns = calc.calculate_voyage_costs(
            cargo_tonnage=75_000.0,
            num_voyages=4,
            spot_rates=[22.50, 23.10, 21.80, 22.40],
            cvc_rate=cvc_rate,
        )
        for v in breakdowns:
            assert v.cvc_voyage_total < v.spot_voyage_total
            assert v.voyage_savings > 0.0

    def test_zero_cvc_discount_equal_freight(self):
        """With 0% discount (same rate), spot and CVC freight costs are equal."""
        calc = _make_calculator()
        rate = 22.50
        breakdowns = calc.calculate_voyage_costs(
            cargo_tonnage=75_000.0,
            num_voyages=1,
            spot_rates=[rate],
            cvc_rate=rate,
        )
        v = breakdowns[0]
        assert v.spot_freight_cost == v.cvc_freight_cost
        assert v.spot_voyage_total == v.cvc_voyage_total
        assert v.voyage_savings == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 5. VoyageCostCalculator — Input Validation
# ─────────────────────────────────────────────────────────────────────────────

class TestVoyageCostCalculatorValidation:
    """Verifies invalid inputs raise ValueError."""

    def test_negative_cargo_tonnage_raises(self):
        calc = VoyageCostCalculator()
        with pytest.raises(ValueError, match="cargo_tonnage"):
            calc.calculate_voyage_costs(
                cargo_tonnage=-1.0,
                num_voyages=1,
                spot_rates=[22.50],
                cvc_rate=21.375,
            )

    def test_zero_num_voyages_raises(self):
        calc = VoyageCostCalculator()
        with pytest.raises(ValueError, match="num_voyages"):
            calc.calculate_voyage_costs(
                cargo_tonnage=75_000.0,
                num_voyages=0,
                spot_rates=[],
                cvc_rate=21.375,
            )

    def test_insufficient_spot_rates_raises(self):
        calc = VoyageCostCalculator()
        with pytest.raises(ValueError, match="spot_rates"):
            calc.calculate_voyage_costs(
                cargo_tonnage=75_000.0,
                num_voyages=4,
                spot_rates=[22.50],  # Only 1 rate for 4 voyages
                cvc_rate=21.375,
            )


# ─────────────────────────────────────────────────────────────────────────────
# 6. VoyageCostCalculator — p10/p90 Rate Assignment
# ─────────────────────────────────────────────────────────────────────────────

class TestQuantileRateAssignment:
    """Verifies p10 and p90 rates are assigned correctly."""

    def test_custom_p10_p90_rates_used(self):
        """Explicitly provided p10/p90 rates are stored per voyage."""
        calc = _make_calculator()
        p10 = [21.00, 21.50, 20.80, 21.20]
        p90 = [24.00, 24.50, 23.80, 24.20]

        breakdowns = calc.calculate_voyage_costs(
            cargo_tonnage=75_000.0,
            num_voyages=4,
            spot_rates=[22.50, 23.10, 21.80, 22.40],
            cvc_rate=21.375,
            p10_rates=p10,
            p90_rates=p90,
        )
        for i, v in enumerate(breakdowns):
            assert v.p10_spot_rate == p10[i], f"Voyage {i+1}: p10 mismatch"
            assert v.p90_spot_rate == p90[i], f"Voyage {i+1}: p90 mismatch"

    def test_default_p10_p90_derived_from_spot(self):
        """When p10/p90 not provided, defaults are spot × 0.95 / spot × 1.08."""
        calc = _make_calculator()
        spot = [22.50]
        breakdowns = calc.calculate_voyage_costs(
            cargo_tonnage=75_000.0,
            num_voyages=1,
            spot_rates=spot,
            cvc_rate=21.375,
        )
        v = breakdowns[0]
        assert v.p10_spot_rate == round(22.50 * 0.95, 2)
        assert v.p90_spot_rate == round(22.50 * 1.08, 2)
