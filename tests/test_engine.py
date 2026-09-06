# -*- coding: utf-8 -*-
"""
Comprehensive pytest suite for:
1. Port & Vessel specifications and lookups
2. Vessel feasibility engine & constraint checks
3. Sagar / Sandheads lighterage router & warning triggers
4. Spot vs. CVC financial evaluator & break-even probability
5. Headline summary generation
6. CLI presentation execution
"""

import math
import re
import pytest

from data.ports import (
    get_port,
    get_all_ports,
    get_indian_hub_ports,
    get_global_partner_ports,
    Port,
)
from data.vessels import (
    get_vessel_class,
    get_all_vessel_classes,
    match_vessel_for_cargo,
    VesselClass,
)
from data.mock_rates import MockRateProvider, OperationalCosts
from engine.feasibility import FeasibilityEngine, VesselFeasibilityResult
from engine.financial_evaluator import FinancialEvaluator, EvaluationResult
import cli


# ======================================================================
# 1. Port Infrastructure & Lookups
# ======================================================================

def test_indian_hub_ports_presence_and_specs():
    """Verify all 7 primary Indian East Coast ports exist with accurate constraints."""
    indian_ports = get_indian_hub_ports()
    assert len(indian_ports) == 7

    port_codes = {p.code for p in indian_ports}
    expected_codes = {"PPA", "VIZAG", "GANGAVARAM", "GOPALPUR", "DHAMRA", "SAGAR_SANDHEADS", "HALDIA"}
    assert port_codes == expected_codes

    # Check specific port parameters
    ppa = get_port("PPA")
    assert ppa.max_draft == 16.5
    assert ppa.max_loa == 300.0
    assert ppa.max_beam == 46.0
    assert ppa.discharge_rate == 25000.0

    vizag = get_port("VIZAG")
    assert vizag.max_draft == 16.5
    assert vizag.max_loa == 280.0
    assert vizag.discharge_rate == 30000.0

    gangavaram = get_port("GANGAVARAM")
    assert gangavaram.max_draft == 18.5
    assert gangavaram.max_loa == 290.0

    dhamra = get_port("DHAMRA")
    assert dhamra.max_draft == 18.0
    assert dhamra.max_loa == 290.0

    haldia = get_port("HALDIA")
    assert haldia.max_draft == 8.5
    assert haldia.max_loa == 230.0
    assert haldia.max_beam == 32.2

    sagar = get_port("SAGAR_SANDHEADS")
    assert sagar.max_draft == 19.0
    assert math.isinf(sagar.max_loa)
    assert math.isinf(sagar.max_beam)
    assert sagar.is_anchorage is True


def test_global_partner_ports():
    """Verify global trading partner ports exist across Australia, Indonesia, Mozambique, US."""
    global_ports = get_global_partner_ports()
    assert len(global_ports) == 8

    # Australia
    hay_point = get_port("Hay Point")
    assert hay_point.max_draft == 17.5
    assert hay_point.country == "Australia"

    newcastle = get_port("Newcastle")
    assert newcastle.max_draft == 15.2
    assert newcastle.country == "Australia"

    # Indonesia
    taboneo = get_port("Taboneo")
    assert taboneo.max_draft == 15.0
    assert taboneo.is_anchorage is True

    banjarmasin = get_port("Banjarmasin")
    assert banjarmasin.max_draft == 9.0

    # Mozambique
    maputo = get_port("Maputo")
    assert maputo.max_draft == 14.0

    beira = get_port("Beira / Nacala")
    assert beira.max_draft == 11.5

    # US
    norfolk = get_port("Norfolk")
    assert norfolk.max_draft == 15.2

    baltimore = get_port("Baltimore")
    assert baltimore.max_draft == 14.3


def test_port_alias_lookups():
    """Verify flexible case-insensitive and alias lookups."""
    assert get_port("ppa").name == "Paradip Port Authority (PPA)"
    assert get_port("Vizag").name == "Visakhapatnam Port Authority (Vizag)"
    assert get_port("smpk").name == "Haldia Dock Complex (SMPK)"
    assert get_port("sandheads").name == "Sagar / Sandheads Deepwater Anchorage"
    assert get_port("dalrymple").name == "Hay Point / Dalrymple"

    with pytest.raises(KeyError):
        get_port("NonExistentPort")


# ======================================================================
# 2. Vessel Class Specifications & Operational Hydrostatics
# ======================================================================

def test_vessel_classes():
    """Verify standard dry bulk fleet dimensions and deadweight categories."""
    vclasses = get_all_vessel_classes()
    assert len(vclasses) == 4

    handy = get_vessel_class("Handysize")
    assert handy.min_dwt == 15000.0
    assert handy.max_dwt == 35000.0
    assert handy.draft == 9.5
    assert handy.loa == 170.0
    assert handy.beam == 27.0

    supra = get_vessel_class("Supramax")
    assert supra.min_dwt == 50000.0
    assert supra.max_dwt == 65000.0
    assert supra.draft == 12.2

    pana = get_vessel_class("Panamax")
    assert pana.min_dwt == 70000.0
    assert pana.max_dwt == 85000.0
    assert pana.draft == 14.5
    assert pana.loa == 229.0
    assert pana.beam == 32.2

    cape = get_vessel_class("Capesize")
    assert cape.min_dwt == 150000.0
    assert cape.max_dwt == 200000.0
    assert cape.draft == 18.5
    assert cape.loa == 290.0
    assert cape.beam == 45.0


def test_vessel_operational_draft():
    """Verify hydrostatic immersion interpolation."""
    cape = get_vessel_class("Capesize")
    # At 0 cargo -> ballast draft
    assert cape.draft_at_tonnage(0) == cape.ballast_draft
    # At 150,000T cargo on 200,000 max DWT:
    # 6.5 + (18.5 - 6.5) * (150000 / 200000) = 6.5 + 12.0 * 0.75 = 15.5m
    assert cape.draft_at_tonnage(150000) == 15.5
    # At full max DWT -> laden draft
    assert cape.draft_at_tonnage(200000) == cape.draft


# ======================================================================
# 3. Feasibility Engine & Sagar/Sandheads Lighterage Routing
# ======================================================================

def test_scenario_a_feasibility_deepwater_direct():
    """
    Scenario A: 150,000T Coal from Hay Point -> Dhamra Port.
    Capesize vessel must be feasible directly with no lighterage required.
    """
    engine = FeasibilityEngine()
    origin = get_port("Hay Point")
    destination = get_port("Dhamra")

    results = engine.evaluate_route(150000, origin, destination)
    best = results[0]

    assert best.vessel_class.code == "CAPESIZE"
    assert best.is_feasible is True
    assert best.is_direct_berth is True
    assert best.lighterage_plan.is_required is False
    assert best.suitability_score > 80.0
    assert len(best.rejection_reasons) == 0


def test_scenario_b_feasibility_shallow_draft_lighterage():
    """
    Scenario B: 75,000T Coal from Newcastle -> Haldia Port.
    Panamax vessel exceeds Haldia draft (8.5m) and must trigger Sagar/Sandheads lighterage.
    """
    engine = FeasibilityEngine()
    origin = get_port("Newcastle")
    destination = get_port("Haldia")

    results = engine.evaluate_route(75000, origin, destination)
    best = results[0]

    assert best.vessel_class.code == "PANAMAX"
    assert best.is_feasible is True
    assert best.is_direct_berth is False
    assert best.lighterage_plan.is_required is True

    # Check lighterage details
    plan = best.lighterage_plan
    assert plan.location == "Sagar / Sandheads Deepwater Anchorage"
    assert plan.excess_draft > 0.0
    assert plan.lightered_tonnage > 0.0
    assert plan.retained_tonnage + plan.lightered_tonnage == 75000.0
    assert plan.lighterage_rate == 6.50
    assert plan.lighterage_cost == round(plan.lightered_tonnage * 6.50, 2)
    assert plan.time_penalty_days == 3.5

    # Check warning string
    expected_warning = "[LIGHTERAGE_REQUIRED] Draft exceeds port maximum. Transshipment required at Sagar/Sandheads."
    assert plan.warning_message == expected_warning
    assert expected_warning in best.warnings


def test_capesize_rejection_at_haldia():
    """Capesize must be rejected at Haldia due to extreme LOA and Beam constraints."""
    engine = FeasibilityEngine()
    origin = get_port("Newcastle")
    haldia = get_port("Haldia")

    cape = get_vessel_class("Capesize")
    result = engine.evaluate_vessel(cape, 75000, origin, haldia)

    assert result.is_feasible is False
    assert result.suitability_score == 0.0
    assert any("max LOA" in r for r in result.rejection_reasons)
    assert any("max Beam" in r for r in result.rejection_reasons)


# ======================================================================
# 4. Mock Rates & Operational Cost Formulas
# ======================================================================

def test_mock_rate_provider_forecasts():
    """Verify forecast rate curves and volatility standard deviations."""
    provider = MockRateProvider()
    rates = provider.get_forecast_rates("NEWCASTLE", "HALDIA", "PANAMAX", 4)
    assert rates == [22.50, 23.10, 21.80, 22.40]

    rates_cape = provider.get_forecast_rates("HAY_POINT", "DHAMRA", "CAPESIZE", 4)
    assert rates_cape == [14.20, 14.50, 13.90, 14.10]

    # Test volatility std
    vol = provider.get_route_volatility("NEWCASTLE", "HALDIA", "PANAMAX")
    assert vol == 5.245


def test_spot_below_breakeven_probability_math():
    """
    Verify standard normal CDF calculation:
    With mean=22.45, breakeven=18.40, std=5.245 -> P(Spot < 18.40) must equal 22.0%.
    """
    provider = MockRateProvider()
    prob = provider.calculate_spot_below_breakeven_probability(
        breakeven_rate=18.40,
        mean_spot_rate=22.45,
        volatility_std=5.245,
    )
    assert round(prob, 1) == 22.0


# ======================================================================
# 5. Financial Evaluator: Spot vs. CVC Break-Even Analysis
# ======================================================================

def test_voyage_cost_formula_components():
    """
    Verifies the exact per-voyage cost formula:
    Voyage Cost = (Freight Rate * Tonnage) + Bunker Adj + Port Charges + (Wait Days * Demurrage) + Lighterage
    """
    fe = FeasibilityEngine()
    evaluator = FinancialEvaluator()

    origin = get_port("Newcastle")
    destination = get_port("Haldia")
    vessel = get_vessel_class("Panamax")
    tonnage = 75000.0

    feasibility_res = fe.evaluate_vessel(vessel, tonnage, origin, destination)

    result = evaluator.evaluate(
        cargo_tonnage=tonnage,
        origin=origin,
        destination=destination,
        vessel=vessel,
        num_voyages=4,
        cvc_discount_pct=5.0,
        lighterage_plan=feasibility_res.lighterage_plan,
    )

    v1 = result.voyages[0]
    expected_freight = round(22.50 * 75000.0, 2)
    expected_bunker = round(1.80 * 75000.0, 2)  # $135,000
    expected_port = 35000.0
    expected_wait_days = 1.5 + 3.5  # 5.0 days
    expected_demurrage = 5.0 * 18000.0  # $90,000
    expected_lighterage = feasibility_res.lighterage_plan.lighterage_cost

    assert v1.spot_freight_cost == expected_freight
    assert v1.bunker_adj_cost == expected_bunker
    assert v1.port_charges == expected_port
    assert v1.wait_days == expected_wait_days
    assert v1.demurrage_cost == expected_demurrage
    assert v1.lighterage_cost == expected_lighterage

    expected_voyage_cost = expected_freight + expected_bunker + expected_port + expected_demurrage + expected_lighterage
    assert v1.spot_voyage_total == expected_voyage_cost


def test_spot_vs_cvc_savings_inr_conversion():
    """Verifies net delta savings conversion from USD to INR at 83.5."""
    evaluator = FinancialEvaluator()
    origin = get_port("Hay Point")
    destination = get_port("Dhamra")
    vessel = get_vessel_class("Capesize")

    result = evaluator.evaluate(
        cargo_tonnage=150000.0,
        origin=origin,
        destination=destination,
        vessel=vessel,
        num_voyages=4,
        cvc_discount_pct=5.0,
    )

    assert result.spot_total_usd > result.cvc_total_usd
    assert result.is_cvc_favorable is True
    assert result.base_case_delta_inr == round(result.base_case_delta_usd * 83.5, 2)
    assert result.base_case_delta_cr == round(result.base_case_delta_inr / 10_000_000.0, 2)


def test_target_headline_structure():
    """
    Verifies dynamic headline formatting:
    'CVC saves ₹{savings_cr:.1f} Cr across {voyages} voyages. Spot only wins if rates fall below ${breakeven:.2f}/T — our forecast puts that probability at {probability:.0f}%.'
    """
    evaluator = FinancialEvaluator()
    origin = get_port("Newcastle")
    destination = get_port("Haldia")
    vessel = get_vessel_class("Panamax")

    # Test with target_cvc_rate=18.40
    result = evaluator.evaluate(
        cargo_tonnage=75000.0,
        origin=origin,
        destination=destination,
        vessel=vessel,
        num_voyages=4,
        target_cvc_rate=18.40,
    )

    pattern = r"CVC saves ₹\d+\.\d+ Cr across 4 voyages\. Spot only wins if rates fall below \$18\.40/T — our forecast puts that probability at 22%\."
    assert re.search(pattern, result.headline_summary) is not None

    # Test with 7.5% discount yielding ₹4.2 Cr
    result_75 = evaluator.evaluate(
        cargo_tonnage=75000.0,
        origin=origin,
        destination=destination,
        vessel=vessel,
        num_voyages=4,
        cvc_discount_pct=7.5,
    )
    assert "CVC saves ₹4.2 Cr across 4 voyages." in result_75.headline_summary


# ======================================================================
# 6. CLI Demo Run Execution
# ======================================================================

def test_cli_demo_execution(capsys):
    """Executes the CLI demo mode to ensure zero unhandled exceptions."""
    cli.run_demo_scenarios()
    # If it completed without raising an exception, test passes!
