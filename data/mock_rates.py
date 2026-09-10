"""
Mock Freight Rate Provider & Maritime Operational Cost Parameters.
Simulates ML time-series freight forecast curves, operational surcharges,
and normal-distribution probability models for spot vs. CVC decision evaluation.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math


@dataclass(frozen=True)
class OperationalCosts:
    bunker_adjustment_per_ton: float = 1.80  # USD / Ton
    port_charges_per_call: float = 35000.0  # USD / Port Call
    demurrage_rate_per_day: float = 18000.0  # USD / Day
    standard_wait_days: float = 1.5  # Standard waiting days at berth/anchorage
    lighterage_rate_per_ton: float = 6.50  # USD / Lightered Ton at Sagar/Sandheads
    lighterage_time_penalty_days: float = 3.5  # Operational delay for STS lighterage
    usd_to_inr: float = 83.50  # Fixed operational exchange rate (1 USD = 83.5 INR)


@dataclass
class RouteRateProfile:
    origin_code: str
    destination_code: str
    vessel_code: str
    monthly_rates: List[float]  # Projected rates per voyage/month ($/T)
    volatility_std: float  # Historical/forecast standard deviation ($/T)
    description: str = ""


# Default benchmark route forecast curves
ROUTE_PROFILES: Dict[Tuple[str, str, str], RouteRateProfile] = {
    # Newcastle -> Haldia (Panamax / Kamsarmax coal parcel ~75,000T)
    ("NEWCASTLE", "HALDIA", "PANAMAX"): RouteRateProfile(
        origin_code="NEWCASTLE",
        destination_code="HALDIA",
        vessel_code="PANAMAX",
        monthly_rates=[22.50, 23.10, 21.80, 22.40],
        volatility_std=5.245,  # Standard deviation calibrating 18.40 break-even to 22% prob
        description="Australia East Coast (Newcastle) to Haldia Dock Complex via Sagar STS",
    ),
    # Hay Point -> Dhamra (Capesize heavy coal parcel ~150,000T)
    ("HAY_POINT", "DHAMRA", "CAPESIZE"): RouteRateProfile(
        origin_code="HAY_POINT",
        destination_code="DHAMRA",
        vessel_code="CAPESIZE",
        monthly_rates=[14.20, 14.50, 13.90, 14.10],
        volatility_std=2.60,
        description="Queensland DBCT / Hay Point direct deepwater Capesize to Dhamra Port",
    ),
    # Taboneo -> Vizag (Supramax / Panamax thermal coal parcel ~55,000 - 75,000T)
    ("TABONEO", "VIZAG", "SUPRAMAX"): RouteRateProfile(
        origin_code="TABONEO",
        destination_code="VIZAG",
        vessel_code="SUPRAMAX",
        monthly_rates=[10.80, 11.20, 10.50, 10.90],
        volatility_std=1.85,
        description="South Kalimantan anchorage to Visakhapatnam Port Authority",
    ),
    # Maputo -> Paradip (Panamax coking/steam coal ~75,000T)
    ("MAPUTO", "PPA", "PANAMAX"): RouteRateProfile(
        origin_code="MAPUTO",
        destination_code="PPA",
        vessel_code="PANAMAX",
        monthly_rates=[18.20, 18.60, 17.80, 18.20],
        volatility_std=3.10,
        description="Mozambique Matola terminal to Paradip Port Authority",
    ),
    # Baltimore -> Gangavaram (Capesize / Panamax deepwater ~80,000 - 150,000T)
    ("BALTIMORE", "GANGAVARAM", "PANAMAX"): RouteRateProfile(
        origin_code="BALTIMORE",
        destination_code="GANGAVARAM",
        vessel_code="PANAMAX",
        monthly_rates=[32.50, 33.20, 31.80, 32.40],
        volatility_std=4.50,
        description="US East Coast Chesapeake to Gangavaram Deepwater Port",
    ),
    # Norfolk -> Gangavaram (Capesize ~150,000T)
    ("NORFOLK", "GANGAVARAM", "CAPESIZE"): RouteRateProfile(
        origin_code="NORFOLK",
        destination_code="GANGAVARAM",
        vessel_code="CAPESIZE",
        monthly_rates=[26.50, 27.10, 25.90, 26.30],
        volatility_std=3.80,
        description="Norfolk Hampton Roads deepwater Capesize to Gangavaram Port",
    ),
}


class MockRateProvider:
    """
    Mock Data Provider simulating ML Rate Forecasting outputs,
    maritime operational fees, and normal probability distributions.
    """

    def __init__(self, op_costs: Optional[OperationalCosts] = None):
        self.op_costs = op_costs or OperationalCosts()

    def get_forecast_rates(
        self,
        origin_code: str,
        destination_code: str,
        vessel_code: str,
        num_voyages: int = 4,
    ) -> List[float]:
        """
        Retrieves monthly projected freight rates ($/T) for the given route and vessel.
        Falls back to intelligent distance-weighted synthesis if not explicitly hardcoded.
        """
        key = (origin_code.upper(), destination_code.upper(), vessel_code.upper())
        if key in ROUTE_PROFILES:
            base_rates = ROUTE_PROFILES[key].monthly_rates
            if len(base_rates) >= num_voyages:
                return base_rates[:num_voyages]
            # Extend cycle if more voyages requested
            extended = []
            while len(extended) < num_voyages:
                extended.extend(base_rates)
            return extended[:num_voyages]

        # Dynamic fallback rate generation based on vessel type baseline
        class_base = {
            "HANDYSIZE": 26.00,
            "SUPRAMAX": 18.50,
            "PANAMAX": 20.00,
            "CAPESIZE": 14.50,
        }.get(vessel_code.upper(), 20.00)

        # Minor monthly cyclical variations (+/- 3%)
        rates = []
        for i in range(num_voyages):
            variation = math.sin(i * 0.8) * 0.04 * class_base
            rates.append(round(class_base + variation, 2))
        return rates

    def get_route_volatility(
        self,
        origin_code: str,
        destination_code: str,
        vessel_code: str,
    ) -> float:
        """
        Returns estimated rate standard deviation ($/T) for the route.
        """
        key = (origin_code.upper(), destination_code.upper(), vessel_code.upper())
        if key in ROUTE_PROFILES:
            return ROUTE_PROFILES[key].volatility_std

        # Default standard deviation ~ 18% of mean rate
        rates = self.get_forecast_rates(origin_code, destination_code, vessel_code, 4)
        mean_rate = sum(rates) / len(rates)
        return round(mean_rate * 0.18, 2)

    @staticmethod
    def calculate_spot_below_breakeven_probability(
        breakeven_rate: float,
        mean_spot_rate: float,
        volatility_std: float,
    ) -> float:
        """
        Calculates P(Spot Rate <= BreakEven) using standard normal CDF:
        Phi((BreakEven - mu) / sigma) via math.erf.
        Returns percentage in range [0.0, 100.0].
        """
        if volatility_std <= 0.0:
            return 100.0 if mean_spot_rate <= breakeven_rate else 0.0

        z = (breakeven_rate - mean_spot_rate) / (volatility_std * math.sqrt(2.0))
        prob = 0.5 * (1.0 + math.erf(z))
        return max(0.0, min(100.0, prob * 100.0))
