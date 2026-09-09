"""
Vessel Class Specifications for Dry Bulk Cargo Fleet.
Standardized dimensions, deadweight tonnages (DWT), and dimensional envelopes.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class VesselClass:
    name: str
    code: str
    min_dwt: float
    max_dwt: float
    typical_dwt: float
    draft: float  # Laden draft (meters)
    ballast_draft: float  # Light ballast draft (meters)
    loa: float  # Length Overall (meters)
    beam: float  # Breadth/Beam (meters)
    description: str
    aliases: List[str] = field(default_factory=list)

    @property
    def capacity_range_str(self) -> str:
        return f"{self.min_dwt:,.0f} - {self.max_dwt:,.0f} DWT"

    def draft_at_tonnage(self, cargo_tonnage: float) -> float:
        """
        Computes operational draft based on loaded cargo parcel tonnage.
        Uses hydrostatic immersion interpolation between ballast draft and laden draft.
        """
        if cargo_tonnage <= 0:
            return self.ballast_draft
        load_ratio = min(1.0, max(0.0, cargo_tonnage / self.max_dwt))
        return round(self.ballast_draft + (self.draft - self.ballast_draft) * load_ratio, 2)


VESSEL_CLASSES: Dict[str, VesselClass] = {
    "HANDYSIZE": VesselClass(
        name="Handysize",
        code="HANDYSIZE",
        min_dwt=15000.0,
        max_dwt=35000.0,
        typical_dwt=30000.0,
        draft=9.5,
        ballast_draft=4.5,
        loa=170.0,
        beam=27.0,
        description="Geared flexible dry bulk vessel; accesses draft-restricted regional ports.",
        aliases=["handysize", "handy", "hs"],
    ),
    "SUPRAMAX": VesselClass(
        name="Supramax / Ultramax",
        code="SUPRAMAX",
        min_dwt=50000.0,
        max_dwt=65000.0,
        typical_dwt=58000.0,
        draft=12.2,
        ballast_draft=5.0,
        loa=200.0,
        beam=32.0,
        description="High-versatility geared workhorse; standard for Indonesian and African routes.",
        aliases=["supramax", "ultramax", "supra", "ultra", "supramax / ultramax"],
    ),
    "PANAMAX": VesselClass(
        name="Panamax / Kamsarmax",
        code="PANAMAX",
        min_dwt=70000.0,
        max_dwt=85000.0,
        typical_dwt=75000.0,
        draft=14.5,
        ballast_draft=5.5,
        loa=229.0,
        beam=32.2,
        description="Standard coal and grain carrier; constrained by historical Panama Canal locks.",
        aliases=["panamax", "kamsarmax", "panamax / kamsarmax", "pana"],
    ),
    "CAPESIZE": VesselClass(
        name="Capesize",
        code="CAPESIZE",
        min_dwt=150000.0,
        max_dwt=200000.0,
        typical_dwt=170000.0,
        draft=18.5,
        ballast_draft=6.5,
        loa=290.0,
        beam=45.0,
        description="Heavy deepwater bulk carrier for iron ore and metallurgical coal trade lanes.",
        aliases=["capesize", "cape", "vloc", "capesize bulk"],
    ),
}


def get_vessel_class(identifier: str) -> VesselClass:
    """
    Look up a vessel class by code, name, or alias (case-insensitive).
    """
    clean_id = identifier.strip().lower()

    for code, vclass in VESSEL_CLASSES.items():
        if code.lower() == clean_id:
            return vclass

    for vclass in VESSEL_CLASSES.values():
        if clean_id in vclass.aliases or clean_id == vclass.name.lower():
            return vclass

    for vclass in VESSEL_CLASSES.values():
        for alias in vclass.aliases:
            if clean_id in alias or alias in clean_id:
                return vclass

    valid_classes = ", ".join(v.name for v in VESSEL_CLASSES.values())
    raise KeyError(f"Unknown vessel class '{identifier}'. Supported classes: {valid_classes}")


def get_all_vessel_classes() -> List[VesselClass]:
    """Returns all standard dry bulk vessel classes."""
    return list(VESSEL_CLASSES.values())


def match_vessel_for_cargo(cargo_tonnage: float) -> Optional[VesselClass]:
    """
    Suggests the best-fitting vessel class based on cargo tonnage alone.
    """
    # Check direct range fit
    for vclass in VESSEL_CLASSES.values():
        if vclass.min_dwt <= cargo_tonnage <= vclass.max_dwt:
            return vclass

    # If within tolerance of typical size
    for vclass in VESSEL_CLASSES.values():
        if abs(cargo_tonnage - vclass.typical_dwt) / vclass.typical_dwt <= 0.20:
            return vclass

    # Default to closest capacity
    return min(VESSEL_CLASSES.values(), key=lambda v: abs(v.typical_dwt - cargo_tonnage))
