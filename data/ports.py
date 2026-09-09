"""
Verified Maritime Port Infrastructure Registry.
Includes Primary Indian East Coast Hub Network and Global Trading Partner Ports.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import math


@dataclass(frozen=True)
class Port:
    name: str
    code: str
    country: str
    is_indian_hub: bool
    max_draft: float  # meters
    max_loa: float  # meters (Length Overall)
    max_beam: float  # meters
    discharge_rate: float  # Metric Tons Per Day (TPD)
    load_rate: float  # Metric Tons Per Day (TPD)
    is_anchorage: bool = False
    fair_weather_draft: Optional[float] = None  # meters
    notes: str = ""
    aliases: List[str] = field(default_factory=list)

    @property
    def effective_draft(self) -> float:
        """Returns the operational max draft."""
        return self.max_draft


# ----------------------------------------------------------------------
# 1. Primary Indian East Coast Ports (Core National Hub Network)
# ----------------------------------------------------------------------
INDIAN_EAST_COAST_PORTS: Dict[str, Port] = {
    "PPA": Port(
        name="Paradip Port Authority (PPA)",
        code="PPA",
        country="India",
        is_indian_hub=True,
        max_draft=16.5,
        max_loa=300.0,
        max_beam=46.0,
        discharge_rate=25000.0,
        load_rate=35000.0,
        notes="Deepwater multi-purpose port; handles major coking coal & iron ore volumes.",
        aliases=["paradip", "ppa", "paradip port", "paradip port authority"],
    ),
    "VIZAG": Port(
        name="Visakhapatnam Port Authority (Vizag)",
        code="VIZAG",
        country="India",
        is_indian_hub=True,
        max_draft=16.5,
        max_loa=280.0,
        max_beam=45.0,
        discharge_rate=30000.0,
        load_rate=30000.0,
        notes="Outer harbour takes deep draft vessels; inner harbour draft-restricted.",
        aliases=["visakhapatnam", "vizag", "vpa", "visakhapatnam port authority", "visakhapatnam port"],
    ),
    "GANGAVARAM": Port(
        name="Gangavaram Port",
        code="GANGAVARAM",
        country="India",
        is_indian_hub=True,
        max_draft=18.5,
        max_loa=290.0,
        max_beam=47.0,
        discharge_rate=35000.0,
        load_rate=40000.0,
        notes="Deepest port on East Coast; capable of fully laden Capesize discharge.",
        aliases=["gangavaram", "gangavaram port", "gvp"],
    ),
    "GOPALPUR": Port(
        name="Gopalpur Port",
        code="GOPALPUR",
        country="India",
        is_indian_hub=True,
        max_draft=13.0,
        max_loa=240.0,
        max_beam=36.0,
        discharge_rate=15000.0,
        load_rate=20000.0,
        fair_weather_draft=13.7,
        notes="Fair weather draft expands up to 13.7m; ideal for Supramax / baby Panamax.",
        aliases=["gopalpur", "gopalpur port", "gpl"],
    ),
    "DHAMRA": Port(
        name="Dhamra Port",
        code="DHAMRA",
        country="India",
        is_indian_hub=True,
        max_draft=18.0,
        max_loa=290.0,
        max_beam=47.0,
        discharge_rate=40000.0,
        load_rate=45000.0,
        notes="Ultra-deepwater all-weather mechanized hub; Capesize handling facility.",
        aliases=["dhamra", "dhamra port", "dpcl"],
    ),
    "SAGAR_SANDHEADS": Port(
        name="Sagar / Sandheads Deepwater Anchorage",
        code="SAGAR_SANDHEADS",
        country="India",
        is_indian_hub=True,
        max_draft=19.0,
        max_loa=math.inf,
        max_beam=math.inf,
        discharge_rate=15000.0,
        load_rate=15000.0,
        is_anchorage=True,
        notes="Designated transshipment & lighterage anchorage for shallow Kolkata/Haldia docks.",
        aliases=["sagar", "sandheads", "sagar sandheads", "sagar / sandheads", "sagar-sandheads", "sandheads anchorage"],
    ),
    "HALDIA": Port(
        name="Haldia Dock Complex (SMPK)",
        code="HALDIA",
        country="India",
        is_indian_hub=True,
        max_draft=8.5,
        max_loa=230.0,
        max_beam=32.2,
        discharge_rate=12000.0,
        load_rate=15000.0,
        notes="Shallow riverine dock system; heavy tidal constraint; requires Sagar/Sandheads lighterage for vessels >8.5m.",
        aliases=["haldia", "smpk", "haldia dock complex", "haldia port", "kolkata haldia"],
    ),
}

# ----------------------------------------------------------------------
# 2. Key Global Partner Ports (Inbound Origins & Outbound Destinations)
# ----------------------------------------------------------------------
GLOBAL_PARTNER_PORTS: Dict[str, Port] = {
    "HAY_POINT": Port(
        name="Hay Point / Dalrymple",
        code="HAY_POINT",
        country="Australia",
        is_indian_hub=False,
        max_draft=17.5,
        max_loa=300.0,
        max_beam=50.0,
        discharge_rate=15000.0,
        load_rate=60000.0,
        notes="World premier metallurgical coking coal export terminal; Capesize capable.",
        aliases=["hay point", "dalrymple", "hay point / dalrymple", "dalrymple bay", "dbt", "haypoint"],
    ),
    "NEWCASTLE": Port(
        name="Newcastle",
        code="NEWCASTLE",
        country="Australia",
        is_indian_hub=False,
        max_draft=15.2,
        max_loa=300.0,
        max_beam=47.0,
        discharge_rate=15000.0,
        load_rate=50000.0,
        notes="Major coal export gateway in NSW; handles Panamax and Capesize (draft restricted).",
        aliases=["newcastle", "port of newcastle", "pwat"],
    ),
    "TABONEO": Port(
        name="Taboneo",
        code="TABONEO",
        country="Indonesia",
        is_indian_hub=False,
        max_draft=15.0,
        max_loa=240.0,
        max_beam=35.0,
        discharge_rate=10000.0,
        load_rate=25000.0,
        is_anchorage=True,
        notes="South Kalimantan coal transshipment anchorage; geared STS & floating cranes.",
        aliases=["taboneo", "taboneo anchorage", "taboneo sts"],
    ),
    "BANJARMASIN": Port(
        name="Banjarmasin",
        code="BANJARMASIN",
        country="Indonesia",
        is_indian_hub=False,
        max_draft=9.0,
        max_loa=190.0,
        max_beam=30.0,
        discharge_rate=8000.0,
        load_rate=15000.0,
        notes="River bar draft restrictions; primarily Handysize and Supramax loading.",
        aliases=["banjarmasin", "banjarmasin port", "trisakti"],
    ),
    "MAPUTO": Port(
        name="Maputo",
        code="MAPUTO",
        country="Mozambique",
        is_indian_hub=False,
        max_draft=14.0,
        max_loa=300.0,
        max_beam=35.0,
        discharge_rate=12000.0,
        load_rate=25000.0,
        notes="Deepened access channel; handles chrome, magnetite, and coal exports on Panamax vessels.",
        aliases=["maputo", "port of maputo", "matola"],
    ),
    "BEIRA_NACALA": Port(
        name="Beira / Nacala",
        code="BEIRA_NACALA",
        country="Mozambique",
        is_indian_hub=False,
        max_draft=11.5,
        max_loa=220.0,
        max_beam=32.0,
        discharge_rate=10000.0,
        load_rate=18000.0,
        notes="Moatize coal corridor feeder port; Supramax and Handysize berth capabilities.",
        aliases=["beira", "nacala", "beira / nacala", "beira/nacala", "port of nacala", "port of beira"],
    ),
    "NORFOLK": Port(
        name="Norfolk / Hampton Roads",
        code="NORFOLK",
        country="United States",
        is_indian_hub=False,
        max_draft=15.2,
        max_loa=300.0,
        max_beam=45.0,
        discharge_rate=20000.0,
        load_rate=40000.0,
        notes="US East Coast premier coal terminal (Lamberts Point / Pier IX); Capesize capable.",
        aliases=["norfolk", "hampton roads", "norfolk / hampton roads", "lamberts point", "pier ix"],
    ),
    "BALTIMORE": Port(
        name="Baltimore",
        code="BALTIMORE",
        country="United States",
        is_indian_hub=False,
        max_draft=14.3,
        max_loa=290.0,
        max_beam=35.0,
        discharge_rate=15000.0,
        load_rate=35000.0,
        notes="Chesapeake Bay deepwater coal and bulk export terminal; Panamax capable.",
        aliases=["baltimore", "port of baltimore", "curtis bay", "cnx marine"],
    ),
}

# Unified Registry
ALL_PORTS: Dict[str, Port] = {**INDIAN_EAST_COAST_PORTS, **GLOBAL_PARTNER_PORTS}


def get_port(identifier: str) -> Port:
    """
    Look up a port by code, name, or alias (case-insensitive).
    Raises KeyError if port is not found.
    """
    clean_id = identifier.strip().lower()

    # Exact key match
    for code, port in ALL_PORTS.items():
        if code.lower() == clean_id:
            return port

    # Exact alias match
    for port in ALL_PORTS.values():
        if clean_id in port.aliases:
            return port
        if clean_id == port.name.lower():
            return port

    # Partial / substring match
    for port in ALL_PORTS.values():
        for alias in port.aliases:
            if clean_id in alias or alias in clean_id:
                return port

    valid_ports = ", ".join(sorted(p.code for p in ALL_PORTS.values()))
    raise KeyError(f"Unknown port '{identifier}'. Supported ports: {valid_ports}")


def get_all_ports() -> List[Port]:
    """Returns a list of all registered ports."""
    return list(ALL_PORTS.values())


def get_indian_hub_ports() -> List[Port]:
    """Returns a list of the 7 Indian East Coast ports."""
    return list(INDIAN_EAST_COAST_PORTS.values())


def get_global_partner_ports() -> List[Port]:
    """Returns a list of global partner origin/destination ports."""
    return list(GLOBAL_PARTNER_PORTS.values())
