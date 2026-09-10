"""
Break-Even Analysis Engine for Spot vs. Consecutive Voyage Charter (CVC) Comparison.
Computes locked CVC rates, break-even thresholds, and scenario comparison metrics
for maritime freight procurement decisions.
"""

from dataclasses import dataclass
from typing import Tuple

from data.mock_rates import OperationalCosts


@dataclass
class ScenarioComparison:
    """Result of comparing spot vs. CVC scenarios."""
    is_cvc_favorable: bool    # True when CVC total <= spot total
    delta_usd: float          # Absolute savings (USD): |spot_total - cvc_total|
    delta_inr: float          # Absolute savings converted to INR


class BreakEvenAnalyzer:
    """
    Provides standalone break-even and scenario comparison calculations
    for Spot vs. CVC freight contracts.

    All USD-to-INR conversions use the exchange rate from OperationalCosts.
    """

    def __init__(self, op_costs: OperationalCosts | None = None):
        self.op_costs = op_costs or OperationalCosts()

    def calculate_break_even_rate(
        self,
        cvc_total_usd: float,
        operational_total_usd: float,
        cargo_tonnage: float,
        num_voyages: int,
    ) -> float:
        """
        Computes the spot rate ($/T) at which cumulative spot costs equal
        cumulative CVC costs across all voyages.

        Formula:
            break_even_rate = (cvc_total_usd - operational_total_usd)
                              / (cargo_tonnage × num_voyages)

        Args:
            cvc_total_usd:         Total CVC freight + operational costs (USD)
            operational_total_usd: Total non-freight operational costs (USD)
                                   (bunker + port charges + demurrage + lighterage × N voyages)
            cargo_tonnage:         Cargo size per voyage (metric tons)
            num_voyages:           Number of voyages in the contract window

        Returns:
            Break-even spot rate in USD per metric ton ($/T).
        """
        total_cargo = cargo_tonnage * num_voyages
        return round((cvc_total_usd - operational_total_usd) / total_cargo, 2)

    def calculate_cvc_rate(
        self,
        average_spot_rate: float,
        cvc_discount_pct: float,
    ) -> float:
        """
        Computes the locked CVC freight rate by applying a negotiated discount
        to the average spot rate.

        Formula:
            locked_cvc_rate = average_spot_rate × (1.0 - cvc_discount_pct / 100.0)

        Args:
            average_spot_rate: Average forecasted spot rate ($/T) over the contract window
            cvc_discount_pct:  CVC negotiated discount percentage (range 0.0 – 15.0)

        Returns:
            Locked CVC freight rate in USD per metric ton ($/T).
        """
        discount_factor = 1.0 - (cvc_discount_pct / 100.0)
        return round(average_spot_rate * discount_factor, 2)

    def compare_scenarios(
        self,
        spot_total_usd: float,
        cvc_total_usd: float,
        cargo_tonnage: float,
        num_voyages: int,
    ) -> Tuple[bool, float, float]:
        """
        Compares cumulative spot vs. CVC costs and returns the direction and
        magnitude of savings.

        Args:
            spot_total_usd: Total spot freight + operational costs over N voyages (USD)
            cvc_total_usd:  Total CVC freight + operational costs over N voyages (USD)
            cargo_tonnage:  Cargo size per voyage (metric tons) — kept for future use
            num_voyages:    Number of voyages — kept for future use

        Returns:
            Tuple of:
                is_cvc_favorable (bool): True when CVC total ≤ spot total
                delta_usd (float):       Absolute savings in USD
                delta_inr (float):       Absolute savings converted to INR
        """
        is_cvc_favorable: bool = cvc_total_usd <= spot_total_usd
        delta_usd: float = round(abs(spot_total_usd - cvc_total_usd), 2)
        delta_inr: float = round(delta_usd * self.op_costs.usd_to_inr, 2)
        return is_cvc_favorable, delta_usd, delta_inr
