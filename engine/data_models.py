"""
Core data models for the maritime freight forecasting engine.
Defines shared dataclasses used across backend financial, ML, and evaluator components.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class VoyageCostBreakdown:
    """
    Per-voyage financial breakdown comparing Spot vs. CVC contract costs.

    All monetary values are in USD unless otherwise specified.
    """
    voyage_number: int
    spot_freight_rate: float        # USD/T (p50 ML forecast rate)
    spot_freight_cost: float        # USD (spot_freight_rate × cargo_tonnage)
    cvc_freight_rate: float         # USD/T (locked CVC rate)
    cvc_freight_cost: float         # USD (cvc_freight_rate × cargo_tonnage)
    bunker_adj_cost: float          # USD (fixed bunker adjustment per voyage)
    port_charges: float             # USD (fixed port charges per call)
    wait_days: float                # Days (standard wait + any lighterage penalty)
    demurrage_cost: float           # USD (wait_days × demurrage_rate_per_day)
    lighterage_tonnage: float       # Metric tons transshipped at anchorage
    lighterage_cost: float          # USD (lighterage_tonnage × lighterage_rate)
    spot_voyage_total: float        # USD (spot_freight_cost + bunker + port + demurrage + lighterage)
    cvc_voyage_total: float         # USD (cvc_freight_cost + bunker + port + demurrage + lighterage)
    voyage_savings: float           # USD (spot_voyage_total - cvc_voyage_total)
    p10_spot_rate: float = 0.0     # USD/T (10th percentile bearish forecast)
    p90_spot_rate: float = 0.0     # USD/T (90th percentile bullish forecast)
