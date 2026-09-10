"""
Voyage Cost Calculator — per-voyage freight cost breakdown engine.

Computes spot and CVC per-voyage costs using the formula:
    voyage_total = (freight_rate × cargo_tonnage)
                  + bunker_adjustment
                  + port_charges
                  + (wait_days × demurrage_rate_per_day)
                  + lighterage_cost
"""

from typing import List, Optional

from data.mock_rates import OperationalCosts
from engine.data_models import VoyageCostBreakdown


class VoyageCostCalculator:
    """
    Computes per-voyage cost breakdowns for spot vs. CVC contract comparison.

    Each voyage breakdown includes:
      - Freight cost (rate × tonnage) for both spot and CVC
      - Bunker adjustment cost
      - Port charges
      - Demurrage cost (wait_days × demurrage_rate_per_day)
      - Lighterage cost (if transshipment is required)
      - Voyage totals and savings
    """

    def __init__(self, op_costs: Optional[OperationalCosts] = None):
        self.op_costs = op_costs or OperationalCosts()

    def calculate_voyage_costs(
        self,
        cargo_tonnage: float,
        num_voyages: int,
        spot_rates: List[float],
        cvc_rate: float,
        operational_costs: Optional[OperationalCosts] = None,
        p10_rates: Optional[List[float]] = None,
        p90_rates: Optional[List[float]] = None,
        lighterage_tonnage: float = 0.0,
        lighterage_cost_per_voyage: float = 0.0,
        wait_days_override: Optional[float] = None,
    ) -> List[VoyageCostBreakdown]:
        """
        Computes per-voyage cost breakdowns for spot vs. CVC comparison.

        Args:
            cargo_tonnage: Cargo weight in metric tons.
            num_voyages: Number of voyages to compute (must match len(spot_rates)).
            spot_rates: List of p50 spot freight rates (USD/T) per voyage.
            cvc_rate: Locked CVC freight rate (USD/T), applied uniformly across all voyages.
            operational_costs: Optional override for operational cost parameters.
                               Defaults to instance's op_costs if not provided.
            p10_rates: Optional list of p10 bearish rates per voyage.
                       Defaults to spot_rates × 0.95 if not provided.
            p90_rates: Optional list of p90 bullish rates per voyage.
                       Defaults to spot_rates × 1.08 if not provided.
            lighterage_tonnage: Metric tons transshipped at Sagar/Sandheads.
                                Defaults to 0.0 (no lighterage).
            lighterage_cost_per_voyage: Pre-computed lighterage cost (USD) per voyage.
                                        Defaults to 0.0 (no lighterage).
            wait_days_override: Optional override for wait days per voyage.
                                If None, uses op_costs.standard_wait_days.

        Returns:
            List of VoyageCostBreakdown records, one per voyage.

        Raises:
            ValueError: If num_voyages does not match len(spot_rates), or if
                        cargo_tonnage / num_voyages is invalid.
        """
        if num_voyages <= 0:
            raise ValueError(f"num_voyages must be a positive integer, got {num_voyages}")
        if cargo_tonnage <= 0.0:
            raise ValueError(f"cargo_tonnage must be positive, got {cargo_tonnage}")
        if len(spot_rates) < num_voyages:
            raise ValueError(
                f"spot_rates has {len(spot_rates)} entries but num_voyages={num_voyages}. "
                "Provide at least num_voyages spot rates."
            )

        costs = operational_costs or self.op_costs

        # Resolve optional rate arrays
        if p10_rates is None:
            p10_rates = [round(r * 0.95, 2) for r in spot_rates]
        if p90_rates is None:
            p90_rates = [round(r * 1.08, 2) for r in spot_rates]

        # Fixed operational costs per voyage
        bunker_adj = round(costs.bunker_adjustment_per_ton * cargo_tonnage, 2)
        port_charges = round(costs.port_charges_per_call, 2)

        effective_wait_days = (
            wait_days_override
            if wait_days_override is not None
            else costs.standard_wait_days
        )
        demurrage_cost = round(effective_wait_days * costs.demurrage_rate_per_day, 2)

        operational_per_voyage = round(
            bunker_adj + port_charges + demurrage_cost + lighterage_cost_per_voyage, 2
        )

        breakdowns: List[VoyageCostBreakdown] = []

        for i in range(num_voyages):
            s_rate = spot_rates[i]
            p10_r = p10_rates[i] if i < len(p10_rates) else round(s_rate * 0.95, 2)
            p90_r = p90_rates[i] if i < len(p90_rates) else round(s_rate * 1.08, 2)

            # Freight costs
            spot_freight = round(s_rate * cargo_tonnage, 2)
            cvc_freight = round(cvc_rate * cargo_tonnage, 2)

            # Voyage totals: freight + all operational components
            spot_voyage_total = round(
                spot_freight + bunker_adj + port_charges + demurrage_cost + lighterage_cost_per_voyage,
                2,
            )
            cvc_voyage_total = round(
                cvc_freight + bunker_adj + port_charges + demurrage_cost + lighterage_cost_per_voyage,
                2,
            )
            voyage_savings = round(spot_voyage_total - cvc_voyage_total, 2)

            breakdowns.append(
                VoyageCostBreakdown(
                    voyage_number=i + 1,
                    spot_freight_rate=s_rate,
                    spot_freight_cost=spot_freight,
                    cvc_freight_rate=cvc_rate,
                    cvc_freight_cost=cvc_freight,
                    bunker_adj_cost=bunker_adj,
                    port_charges=port_charges,
                    wait_days=effective_wait_days,
                    demurrage_cost=demurrage_cost,
                    lighterage_tonnage=lighterage_tonnage,
                    lighterage_cost=lighterage_cost_per_voyage,
                    spot_voyage_total=spot_voyage_total,
                    cvc_voyage_total=cvc_voyage_total,
                    voyage_savings=voyage_savings,
                    p10_spot_rate=p10_r,
                    p90_spot_rate=p90_r,
                )
            )

        return breakdowns
