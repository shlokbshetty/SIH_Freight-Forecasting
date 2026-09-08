"""
Spot vs. Consecutive Voyage Charter (CVC) Financial Evaluator.
Models per-voyage freight costs, bunker adjustments, port dues, demurrage penalties,
lighterage transshipment costs, break-even thresholds, and normal forecast probabilities.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import math
import logging

from data.ports import Port, get_port
from data.vessels import VesselClass, get_all_vessel_classes
from data.mock_rates import OperationalCosts, MockRateProvider
from engine.feasibility import FeasibilityEngine, LighteragePlan, VesselFeasibilityResult
from engine.ml_forecaster import MultiQuantileForecaster, MLForecastResult
from engine.data_models import VoyageCostBreakdown  # noqa: F401 — re-exported for backward compat

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    origin: Port
    destination: Port
    vessel_class: VesselClass
    cargo_tonnage: float
    num_voyages: int
    cvc_discount_pct: float
    lighterage_plan: LighteragePlan
    voyages: List[VoyageCostBreakdown]
    spot_freight_total_usd: float
    spot_operational_total_usd: float
    spot_total_usd: float
    spot_total_inr: float
    cvc_freight_total_usd: float
    cvc_operational_total_usd: float
    cvc_total_usd: float
    cvc_total_inr: float
    locked_cvc_rate: float
    average_spot_rate: float
    base_case_delta_usd: float
    base_case_delta_inr: float
    base_case_delta_cr: float  # In Crores (1 Cr = 10,000,000 INR)
    is_cvc_favorable: bool
    breakeven_spot_rate: float
    breakeven_probability_pct: float
    headline_summary: str
    ml_forecast: Optional[MLForecastResult] = None
    p10_spot_total_usd: float = 0.0
    p90_spot_total_usd: float = 0.0

    # Convenience aliases used by FastAPI response serialisation
    @property
    def cargo_tonnage_prop(self) -> float:
        return self.cargo_tonnage


class FinancialEvaluator:
    """
    Evaluates cumulative cost structures between Spot market chartering
    and Consecutive Voyage Charter (CVC) agreements using ML Quantile predictions.
    """

    def __init__(
        self,
        rate_provider: Optional[MockRateProvider] = None,
        ml_forecaster: Optional[MultiQuantileForecaster] = None,
        op_costs: Optional[OperationalCosts] = None,
    ):
        self.rate_provider = rate_provider or MockRateProvider(op_costs)
        self.ml_forecaster = ml_forecaster or MultiQuantileForecaster()
        self.op_costs = self.rate_provider.op_costs

    def evaluate(
        self,
        cargo_tonnage: float,
        origin: Port,
        destination: Port,
        vessel: VesselClass,
        num_voyages: int = 4,
        cvc_discount_pct: float = 5.0,
        lighterage_plan: Optional[LighteragePlan] = None,
        target_cvc_rate: Optional[float] = None,
        use_ml: bool = True,
        ml_forecast: Optional[MLForecastResult] = None,
    ) -> EvaluationResult:
        """
        Executes financial evaluation for Spot vs. CVC contracts over N voyages.
        """
        lighterage = lighterage_plan or LighteragePlan()

        # 1. Retrieve spot freight rates (ML Quantile Forecast or Mock fallback)
        forecast_res = ml_forecast
        if use_ml and forecast_res is None:
            try:
                forecast_res = self.ml_forecaster.predict_route(
                    origin_code=origin.code,
                    destination_code=destination.code,
                    vessel_code=vessel.code,
                    num_voyages=num_voyages,
                )
            except Exception:
                forecast_res = None

        if forecast_res is not None:
            spot_rates = forecast_res.p50_rates[:num_voyages]
            p10_rates = forecast_res.p10_rates[:num_voyages]
            p90_rates = forecast_res.p90_rates[:num_voyages]
            volatility_std = forecast_res.volatility_std
        else:
            spot_rates = self.rate_provider.get_forecast_rates(
                origin_code=origin.code,
                destination_code=destination.code,
                vessel_code=vessel.code,
                num_voyages=num_voyages,
            )
            p10_rates = [round(r * 0.95, 2) for r in spot_rates]
            p90_rates = [round(r * 1.08, 2) for r in spot_rates]
            volatility_std = self.rate_provider.get_route_volatility(
                origin_code=origin.code,
                destination_code=destination.code,
                vessel_code=vessel.code,
            )

        avg_spot_rate = round(sum(spot_rates) / len(spot_rates), 2)

        # 2. Determine locked CVC freight rate
        if target_cvc_rate is not None:
            locked_cvc_rate = round(target_cvc_rate, 2)
        else:
            discount_factor = 1.0 - (cvc_discount_pct / 100.0)
            locked_cvc_rate = round(avg_spot_rate * discount_factor, 2)

        # 3. Operational Terms Calculation
        bunker_adj = round(self.op_costs.bunker_adjustment_per_ton * cargo_tonnage, 2)
        port_charges = round(self.op_costs.port_charges_per_call, 2)

        effective_wait_days = self.op_costs.standard_wait_days
        if lighterage.is_required:
            effective_wait_days += lighterage.time_penalty_days

        demurrage_cost = round(effective_wait_days * self.op_costs.demurrage_rate_per_day, 2)
        lighterage_cost_per_voyage = round(lighterage.lighterage_cost, 2)

        operational_per_voyage = round(
            bunker_adj + port_charges + demurrage_cost + lighterage_cost_per_voyage, 2
        )

        # 4. Voyage-by-Voyage Breakdown
        voyage_breakdowns: List[VoyageCostBreakdown] = []
        spot_freight_total = 0.0
        cvc_freight_total = 0.0
        spot_total_usd = 0.0
        cvc_total_usd = 0.0
        p10_freight_total = 0.0
        p90_freight_total = 0.0

        for i in range(num_voyages):
            s_rate = spot_rates[i]
            p10_r = p10_rates[i]
            p90_r = p90_rates[i]

            s_freight = round(s_rate * cargo_tonnage, 2)
            c_freight = round(locked_cvc_rate * cargo_tonnage, 2)
            p10_freight = round(p10_r * cargo_tonnage, 2)
            p90_freight = round(p90_r * cargo_tonnage, 2)

            s_voyage_cost = round(s_freight + operational_per_voyage, 2)
            c_voyage_cost = round(c_freight + operational_per_voyage, 2)
            v_savings = round(s_voyage_cost - c_voyage_cost, 2)

            spot_freight_total += s_freight
            cvc_freight_total += c_freight
            p10_freight_total += p10_freight
            p90_freight_total += p90_freight

            spot_total_usd += s_voyage_cost
            cvc_total_usd += c_voyage_cost

            voyage_breakdowns.append(
                VoyageCostBreakdown(
                    voyage_number=i + 1,
                    spot_freight_rate=s_rate,
                    spot_freight_cost=s_freight,
                    cvc_freight_rate=locked_cvc_rate,
                    cvc_freight_cost=c_freight,
                    bunker_adj_cost=bunker_adj,
                    port_charges=port_charges,
                    wait_days=effective_wait_days,
                    demurrage_cost=demurrage_cost,
                    lighterage_tonnage=lighterage.lightered_tonnage,
                    lighterage_cost=lighterage_cost_per_voyage,
                    spot_voyage_total=s_voyage_cost,
                    cvc_voyage_total=c_voyage_cost,
                    voyage_savings=v_savings,
                    p10_spot_rate=p10_r,
                    p90_spot_rate=p90_r,
                )
            )

        # Round totals
        spot_freight_total = round(spot_freight_total, 2)
        cvc_freight_total = round(cvc_freight_total, 2)
        spot_operational_total = round(operational_per_voyage * num_voyages, 2)
        cvc_operational_total = round(operational_per_voyage * num_voyages, 2)
        spot_total_usd = round(spot_total_usd, 2)
        cvc_total_usd = round(cvc_total_usd, 2)

        p10_spot_total_usd = round(p10_freight_total + spot_operational_total, 2)
        p90_spot_total_usd = round(p90_freight_total + spot_operational_total, 2)

        # Base case delta
        delta_usd = round(spot_total_usd - cvc_total_usd, 2)
        is_cvc_favorable = delta_usd >= 0.0

        exchange_rate = self.op_costs.usd_to_inr
        spot_total_inr = round(spot_total_usd * exchange_rate, 2)
        cvc_total_inr = round(cvc_total_usd * exchange_rate, 2)
        delta_inr = round(abs(delta_usd) * exchange_rate, 2)
        delta_cr = round(delta_inr / 10_000_000.0, 2)

        # 5. Break-Even Spot Rate ($/T)
        total_cargo_handled = cargo_tonnage * num_voyages
        breakeven_spot_rate = round(
            (cvc_total_usd - spot_operational_total) / total_cargo_handled, 2
        )

        # 6. Forecast Probability Calculation
        if forecast_res is not None:
            # Multi-Quantile implied probability
            # Standard deviation calibrating Newcastle to Haldia break-even
            key = (origin.code.upper(), destination.code.upper(), vessel.code.upper())
            route_vol = self.rate_provider.get_route_volatility(origin.code, destination.code, vessel.code)
            effective_vol = route_vol if route_vol > 0 else volatility_std
            prob_below_breakeven = MultiQuantileForecaster.calculate_breakeven_probability(
                breakeven_rate=breakeven_spot_rate,
                mean_spot_rate=avg_spot_rate,
                volatility_std=effective_vol,
            )
        else:
            prob_below_breakeven = self.rate_provider.calculate_spot_below_breakeven_probability(
                breakeven_rate=breakeven_spot_rate,
                mean_spot_rate=avg_spot_rate,
                volatility_std=volatility_std,
            )

        # 7. Dynamic Headline Summary
        if is_cvc_favorable:
            headline = (
                f"CVC saves ₹{delta_cr:.1f} Cr across {num_voyages} voyages. "
                f"Spot only wins if rates fall below ${breakeven_spot_rate:.2f}/T — "
                f"our forecast puts that probability at {prob_below_breakeven:.0f}%."
            )
        else:
            prob_spot_wins = round(100.0 - prob_below_breakeven)
            headline = (
                f"Spot saves ₹{delta_cr:.1f} Cr across {num_voyages} voyages. "
                f"CVC only wins if rates rise above ${breakeven_spot_rate:.2f}/T — "
                f"our forecast puts that probability at {prob_spot_wins:.0f}%."
            )

        return EvaluationResult(
            origin=origin,
            destination=destination,
            vessel_class=vessel,
            cargo_tonnage=cargo_tonnage,
            num_voyages=num_voyages,
            cvc_discount_pct=cvc_discount_pct,
            lighterage_plan=lighterage,
            voyages=voyage_breakdowns,
            spot_freight_total_usd=spot_freight_total,
            spot_operational_total_usd=spot_operational_total,
            spot_total_usd=spot_total_usd,
            spot_total_inr=spot_total_inr,
            cvc_freight_total_usd=cvc_freight_total,
            cvc_operational_total_usd=cvc_operational_total,
            cvc_total_usd=cvc_total_usd,
            cvc_total_inr=cvc_total_inr,
            locked_cvc_rate=locked_cvc_rate,
            average_spot_rate=avg_spot_rate,
            base_case_delta_usd=delta_usd,
            base_case_delta_inr=delta_inr,
            base_case_delta_cr=delta_cr,
            is_cvc_favorable=is_cvc_favorable,
            breakeven_spot_rate=breakeven_spot_rate,
            breakeven_probability_pct=round(prob_below_breakeven, 1),
            headline_summary=headline,
            ml_forecast=forecast_res,
            p10_spot_total_usd=p10_spot_total_usd,
            p90_spot_total_usd=p90_spot_total_usd,
        )

    # ─── Task 1.12: Vessel filtering and time horizon helpers ──────────────

    def get_supported_vessels(
        self,
        cargo_tonnage: float,
        origin: Port,
        destination: Port,
    ) -> List[VesselFeasibilityResult]:
        """
        Returns a ranked list of feasible vessel classes for the given cargo and route.

        Filters vessels by feasibility (draft, LOA, beam constraints) using FeasibilityEngine
        and returns them ranked by suitability_score descending.

        Args:
            cargo_tonnage: Cargo size in metric tons.
            origin:        Origin port object.
            destination:   Destination port object.

        Returns:
            List of VesselFeasibilityResult sorted by suitability_score (highest first),
            including only feasible vessels (is_feasible=True).
        """
        engine = FeasibilityEngine(op_costs=self.op_costs)
        all_results = engine.evaluate_route(cargo_tonnage, origin, destination)
        feasible = [r for r in all_results if r.is_feasible]
        logger.info(
            "get_supported_vessels: %d/%d vessels feasible for %s→%s %.0fT",
            len(feasible), len(all_results), origin.code, destination.code, cargo_tonnage,
        )
        return feasible

    @staticmethod
    def get_voyage_count(time_horizon_months: int) -> int:
        """
        Maps a time horizon (months) to the number of voyages in the evaluation window.

        Mapping (Newcastle–Haldia Panamax reference):
            1 month  → 1 voyage
            3 months → 4 voyages
            6 months → 8 voyages

        For unsupported time horizons, falls back proportionally (1 voyage per ~3 weeks).

        Args:
            time_horizon_months: Horizon in calendar months (positive integer).

        Returns:
            Integer number of voyages for the evaluation window.
        """
        _HORIZON_MAP = {1: 1, 3: 4, 6: 8}
        if time_horizon_months in _HORIZON_MAP:
            return _HORIZON_MAP[time_horizon_months]

        # Fallback: approximate 1 voyage per 0.75 months (standard 3-week cycle)
        voyages = max(1, round(time_horizon_months / 0.75))
        logger.warning(
            "get_voyage_count: non-standard horizon %d months → %d voyages (estimated)",
            time_horizon_months, voyages,
        )
        return voyages
