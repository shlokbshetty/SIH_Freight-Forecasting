"""
Core Maritime Feasibility Engine & Sagar/Sandheads Lighterage Router.
Evaluates dimensional constraints (Draft, LOA, Beam) at Origin and Destination ports,
determines optimal vessel class rankings, and automates deepwater anchorage transshipment routing.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math

from data.ports import Port, get_port, INDIAN_EAST_COAST_PORTS
from data.vessels import VesselClass, get_all_vessel_classes, get_vessel_class
from data.mock_rates import OperationalCosts


@dataclass
class DimensionalCheck:
    dimension_name: str
    vessel_val: float
    port_max_val: float
    is_passed: bool
    clearance_margin: float  # port_max - vessel_val
    notes: str = ""


@dataclass
class LighteragePlan:
    is_required: bool = False
    location: Optional[str] = None
    excess_draft: float = 0.0  # meters
    lightered_tonnage: float = 0.0  # metric tons
    retained_tonnage: float = 0.0  # metric tons arriving at dock
    lighterage_rate: float = 6.50  # USD/ton
    lighterage_cost: float = 0.0  # USD
    time_penalty_days: float = 3.5  # days
    warning_message: Optional[str] = None


@dataclass
class VesselFeasibilityResult:
    vessel_class: VesselClass
    is_feasible: bool
    is_direct_berth: bool
    suitability_score: float  # 0 to 100
    origin_checks: List[DimensionalCheck]
    destination_checks: List[DimensionalCheck]
    lighterage_plan: LighteragePlan
    utilization_pct: float  # Cargo tonnage / Vessel max DWT
    warnings: List[str] = field(default_factory=list)
    rejection_reasons: List[str] = field(default_factory=list)


class FeasibilityEngine:
    """
    Evaluates dry bulk vessel feasibility for origin-destination pairs.
    Handles Sagar/Sandheads deepwater anchorage lighterage routing.
    """

    def __init__(self, op_costs: Optional[OperationalCosts] = None):
        self.op_costs = op_costs or OperationalCosts()

    def evaluate_vessel(
        self,
        vessel: VesselClass,
        cargo_tonnage: float,
        origin: Port,
        destination: Port,
    ) -> VesselFeasibilityResult:
        """
        Evaluates a single vessel class against cargo tonnage, origin, and destination constraints.
        """
        warnings: List[str] = []
        rejection_reasons: List[str] = []

        # 1. Deadweight / Capacity fit
        utilization_pct = min(100.0, (cargo_tonnage / vessel.max_dwt) * 100.0)
        if cargo_tonnage > vessel.max_dwt * 1.15:
            warnings.append(
                f"Cargo {cargo_tonnage:,.0f}T exceeds vessel max capacity {vessel.max_dwt:,.0f} DWT (Multiple parcels required)."
            )
        elif cargo_tonnage < vessel.min_dwt * 0.70:
            warnings.append(
                f"Cargo {cargo_tonnage:,.0f}T underutilizes vessel capacity {vessel.capacity_range_str}."
            )

        # Operating draft based on actual loaded cargo tonnage
        operating_draft = vessel.draft_at_tonnage(cargo_tonnage)

        # 2. Origin Port Dimensional Checks
        origin_draft_check = DimensionalCheck(
            dimension_name="Draft",
            vessel_val=operating_draft,
            port_max_val=origin.max_draft,
            is_passed=(operating_draft <= origin.max_draft),
            clearance_margin=round(origin.max_draft - operating_draft, 2),
            notes=f"Laden draft: {vessel.draft}m, Operating draft at {cargo_tonnage:,.0f}T: {operating_draft}m",
        )
        origin_loa_check = DimensionalCheck(
            dimension_name="LOA",
            vessel_val=vessel.loa,
            port_max_val=origin.max_loa,
            is_passed=(vessel.loa <= origin.max_loa),
            clearance_margin=round(origin.max_loa - vessel.loa, 2),
        )
        origin_beam_check = DimensionalCheck(
            dimension_name="Beam",
            vessel_val=vessel.beam,
            port_max_val=origin.max_beam,
            is_passed=(vessel.beam <= origin.max_beam),
            clearance_margin=round(origin.max_beam - vessel.beam, 2),
        )

        origin_checks = [origin_draft_check, origin_loa_check, origin_beam_check]
        origin_passed = all(c.is_passed for c in origin_checks)

        if not origin_draft_check.is_passed:
            rejection_reasons.append(
                f"Origin {origin.name} max draft ({origin.max_draft}m) exceeds vessel operating draft ({operating_draft}m)."
            )
        if not origin_loa_check.is_passed:
            rejection_reasons.append(
                f"Origin {origin.name} max LOA ({origin.max_loa}m) exceeds vessel LOA ({vessel.loa}m)."
            )
        if not origin_beam_check.is_passed:
            rejection_reasons.append(
                f"Origin {origin.name} max Beam ({origin.max_beam}m) exceeds vessel Beam ({vessel.beam}m)."
            )

        # 3. Destination Port Dimensional Checks
        dest_loa_check = DimensionalCheck(
            dimension_name="LOA",
            vessel_val=vessel.loa,
            port_max_val=destination.max_loa,
            is_passed=(vessel.loa <= destination.max_loa),
            clearance_margin=round(destination.max_loa - vessel.loa, 2),
        )
        dest_beam_check = DimensionalCheck(
            dimension_name="Beam",
            vessel_val=vessel.beam,
            port_max_val=destination.max_beam,
            is_passed=(vessel.beam <= destination.max_beam),
            clearance_margin=round(destination.max_beam - vessel.beam, 2),
        )
        dest_draft_check = DimensionalCheck(
            dimension_name="Draft",
            vessel_val=operating_draft,
            port_max_val=destination.max_draft,
            is_passed=(operating_draft <= destination.max_draft),
            clearance_margin=round(destination.max_draft - operating_draft, 2),
            notes=f"Laden draft: {vessel.draft}m, Operating draft at {cargo_tonnage:,.0f}T: {operating_draft}m",
        )

        destination_checks = [dest_draft_check, dest_loa_check, dest_beam_check]

        if not dest_loa_check.is_passed:
            rejection_reasons.append(
                f"Destination {destination.name} max LOA ({destination.max_loa}m) exceeds vessel LOA ({vessel.loa}m)."
            )
        if not dest_beam_check.is_passed:
            rejection_reasons.append(
                f"Destination {destination.name} max Beam ({destination.max_beam}m) exceeds vessel Beam ({vessel.beam}m)."
            )

        # 4. Lighterage & Transshipment Logic
        lighterage_plan = LighteragePlan()
        is_direct_berth = dest_draft_check.is_passed

        if not dest_draft_check.is_passed:
            # Check if destination can be served by Sagar / Sandheads Deepwater Anchorage
            sagar = INDIAN_EAST_COAST_PORTS["SAGAR_SANDHEADS"]
            can_lighter = (
                destination.is_indian_hub
                and operating_draft <= sagar.max_draft
                and dest_loa_check.is_passed
                and dest_beam_check.is_passed
            )

            if can_lighter:
                excess_draft = round(operating_draft - destination.max_draft, 2)
                immersion_fraction = (operating_draft - destination.max_draft) / operating_draft
                lightered_tonnage = round(cargo_tonnage * immersion_fraction, 2)
                retained_tonnage = round(cargo_tonnage - lightered_tonnage, 2)
                lighterage_cost = round(lightered_tonnage * self.op_costs.lighterage_rate_per_ton, 2)
                warning_msg = "[LIGHTERAGE_REQUIRED] Draft exceeds port maximum. Transshipment required at Sagar/Sandheads."

                lighterage_plan = LighteragePlan(
                    is_required=True,
                    location=sagar.name,
                    excess_draft=excess_draft,
                    lightered_tonnage=lightered_tonnage,
                    retained_tonnage=retained_tonnage,
                    lighterage_rate=self.op_costs.lighterage_rate_per_ton,
                    lighterage_cost=lighterage_cost,
                    time_penalty_days=self.op_costs.lighterage_time_penalty_days,
                    warning_message=warning_msg,
                )
                warnings.append(warning_msg)
            else:
                rejection_reasons.append(
                    f"Destination {destination.name} max draft ({destination.max_draft}m) exceeded by vessel draft ({vessel.draft}m), and Sagar/Sandheads transshipment is not viable."
                )

        # 5. Overall Feasibility
        is_feasible = origin_passed and (is_direct_berth or lighterage_plan.is_required) and dest_loa_check.is_passed and dest_beam_check.is_passed

        # 6. Suitability Scoring (0 - 100)
        suitability_score = self._compute_suitability_score(
            vessel=vessel,
            cargo_tonnage=cargo_tonnage,
            is_feasible=is_feasible,
            is_direct_berth=is_direct_berth,
            lighterage_plan=lighterage_plan,
            origin_checks=origin_checks,
            destination_checks=destination_checks,
        )

        return VesselFeasibilityResult(
            vessel_class=vessel,
            is_feasible=is_feasible,
            is_direct_berth=is_direct_berth,
            suitability_score=round(suitability_score, 1),
            origin_checks=origin_checks,
            destination_checks=destination_checks,
            lighterage_plan=lighterage_plan,
            utilization_pct=round(utilization_pct, 1),
            warnings=warnings,
            rejection_reasons=rejection_reasons,
        )

    def _compute_suitability_score(
        self,
        vessel: VesselClass,
        cargo_tonnage: float,
        is_feasible: bool,
        is_direct_berth: bool,
        lighterage_plan: LighteragePlan,
        origin_checks: List[DimensionalCheck],
        destination_checks: List[DimensionalCheck],
    ) -> float:
        """
        Computes composite suitability score between 0 and 100:
        1. Feasibility gate: 0.0 if unfeasible.
        2. Cargo parcel fit (50 pts max):
           - Full points if cargo fits within [min_dwt, max_dwt].
           - Heavy decay if cargo exceeds max_dwt (requiring multiple vessels/parcels).
           - Proportional decay if cargo underutilizes vessel capacity.
        3. Berthing & Transshipment mode (25 pts max):
           - 25 pts for direct berthing at dock.
           - 12 pts if lighterage transshipment is required.
        4. Operational safety margins (25 pts max):
           - Under-keel clearance (UKC draft headroom): up to 10 pts.
           - LOA clearance: up to 10 pts.
           - Beam clearance: up to 5 pts.
        """
        if not is_feasible:
            return 0.0

        # 1. Cargo deadweight fit (50 pts)
        if vessel.min_dwt <= cargo_tonnage <= vessel.max_dwt:
            fit_pts = 50.0
        elif cargo_tonnage > vessel.max_dwt:
            fit_pts = 50.0 * ((vessel.max_dwt / cargo_tonnage) ** 1.5)
        else:
            fit_pts = 50.0 * (cargo_tonnage / vessel.min_dwt)

        # 2. Berthing / Transshipment mode (25 pts)
        if is_direct_berth:
            berth_pts = 25.0
        elif lighterage_plan.is_required:
            berth_pts = 12.0
        else:
            berth_pts = 0.0

        # 3. Operational safety margins (25 pts)
        # Average clearances between origin and destination
        draft_margins = [c.clearance_margin for c in origin_checks + destination_checks if c.dimension_name == "Draft"]
        loa_margins = [c.clearance_margin for c in origin_checks + destination_checks if c.dimension_name == "LOA" and not math.isinf(c.port_max_val)]
        beam_margins = [c.clearance_margin for c in origin_checks + destination_checks if c.dimension_name == "Beam" and not math.isinf(c.port_max_val)]

        avg_draft_margin = sum(max(0.0, m) for m in draft_margins) / len(draft_margins) if draft_margins else 0.0
        avg_loa_margin = sum(max(0.0, m) for m in loa_margins) / len(loa_margins) if loa_margins else 0.0
        avg_beam_margin = sum(max(0.0, m) for m in beam_margins) / len(beam_margins) if beam_margins else 0.0

        d_score = min(10.0, avg_draft_margin * 4.0)
        loa_score = min(10.0, avg_loa_margin * 0.15)
        beam_score = min(5.0, avg_beam_margin * 0.5)

        safety_pts = d_score + loa_score + beam_score

        total_score = fit_pts + berth_pts + safety_pts
        return round(min(100.0, max(0.0, total_score)), 1)

    def evaluate_route(
        self,
        cargo_tonnage: float,
        origin: Port,
        destination: Port,
    ) -> List[VesselFeasibilityResult]:
        """
        Evaluates all registered vessel classes for the given cargo and route.
        Returns results ranked by suitability score in descending order.
        """
        results: List[VesselFeasibilityResult] = []
        for vclass in get_all_vessel_classes():
            result = self.evaluate_vessel(
                vessel=vclass,
                cargo_tonnage=cargo_tonnage,
                origin=origin,
                destination=destination,
            )
            results.append(result)

        # Sort descending by suitability score
        results.sort(key=lambda r: r.suitability_score, reverse=True)
        return results

    def get_best_vessel(
        self,
        cargo_tonnage: float,
        origin: Port,
        destination: Port,
    ) -> Optional[VesselFeasibilityResult]:
        """
        Returns the top-ranked feasible vessel for the cargo and route, or None if none feasible.
        """
        ranked = self.evaluate_route(cargo_tonnage, origin, destination)
        feasible = [r for r in ranked if r.is_feasible]
        return feasible[0] if feasible else None
