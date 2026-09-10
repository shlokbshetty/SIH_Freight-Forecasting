"""Port and vessel reference data.

Mirrors src/data/ports.ts and src/data/vessels.ts on the frontend. Until the
React app is switched over to /api/ports, the two copies must be kept in step;
the frontend is the source of truth for presentation, this is the source of
truth for anything the server computes.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Literal

CongestionLevel = Literal["low", "medium", "high"]
VesselClass = Literal["Handysize", "Supramax", "Panamax", "Capesize"]

VESSEL_CLASSES: list[VesselClass] = ["Handysize", "Supramax", "Panamax", "Capesize"]


@dataclass(frozen=True)
class DischargePort:
    id: str
    name: str
    lat: float
    lng: float
    max_draft_m: float
    current_draft_m: float
    max_loa_m: float
    berth_count: int
    berths_available: int
    cargo_rate_tpd: int
    lighterage_required: bool
    congestion_level: CongestionLevel
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LoadingPort:
    id: str
    name: str
    country: str
    lat: float
    lng: float
    commodities: tuple[str, ...] = field(default=())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["commodities"] = list(self.commodities)
        return d


@dataclass(frozen=True)
class VesselSpec:
    vessel_class: VesselClass
    dwt_min: int
    dwt_max: int
    loa_m: float
    beam_m: float
    laden_draft_m: float
    ballast_draft_m: float
    speed_kts: float
    color: str
    description: str

    def to_dict(self) -> dict:
        return asdict(self)


# ── The seven East Coast India discharge ports ────────────────────────────────

DISCHARGE_PORTS: list[DischargePort] = [
    DischargePort("paradip", "Paradip", 20.2649, 86.6800, 14.5, 14.0, 270, 8, 3, 35_000, False, "medium"),
    DischargePort("vizag", "Visakhapatnam (Vizag)", 17.6868, 83.2185, 16.0, 15.5, 300, 12, 5, 45_000, False, "low"),
    DischargePort("gangavaram", "Gangavaram", 17.6260, 83.2280, 18.5, 18.0, 350, 6, 2, 50_000, False, "low"),
    DischargePort(
        "gopalpur", "Gopalpur", 19.2600, 84.9100, 10.5, 9.8, 190, 3, 1, 18_000, False, "medium",
        "Shallow port - Handysize only at high tide",
    ),
    DischargePort("dhamra", "Dhamra", 20.4717, 86.8981, 17.0, 16.5, 320, 4, 2, 40_000, False, "low"),
    DischargePort(
        "sagar-sandheads", "Sagar / Sandheads", 21.6400, 88.0600, 8.5, 8.0, 160, 0, 0, 0, True, "high",
        "Anchorage / lighterage point. Capesize and Panamax must lighten here before proceeding to Haldia.",
    ),
    DischargePort(
        "haldia", "Haldia", 22.0257, 88.1015, 8.2, 7.9, 170, 7, 2, 20_000, False, "high",
        "Tidal window critical. River approach with strict LOA and draft limits.",
    ),
]

DISCHARGE_PORTS_BY_ID: dict[str, DischargePort] = {p.id: p for p in DISCHARGE_PORTS}


# ── Origin load ports ─────────────────────────────────────────────────────────

LOADING_PORTS: list[LoadingPort] = [
    LoadingPort("newcastle", "Newcastle", "Australia", -32.9283, 151.7817, ("Coal",)),
    LoadingPort("gladstone", "Gladstone", "Australia", -23.8427, 151.2580, ("Coal", "Bauxite")),
    LoadingPort("abbot-point", "Abbot Point", "Australia", -19.8800, 148.0900, ("Coal",)),
    LoadingPort("hampton-roads", "Hampton Roads", "USA", 36.9460, -76.3200, ("Coal",)),
    LoadingPort("beira", "Beira", "Mozambique", -19.8436, 34.8380, ("Coal",)),
    LoadingPort("nacala", "Nacala", "Mozambique", -14.5480, 40.6820, ("Coal",)),
    LoadingPort("murmansk", "Murmansk", "Russia", 68.9585, 33.0827, ("Coal",)),
    LoadingPort("kalimantan", "Kalimantan", "Indonesia", -1.6815, 116.3690, ("Coal",)),
    LoadingPort("balikpapan", "Balikpapan", "Indonesia", -1.2675, 116.8289, ("Coal", "Palm Oil")),
]

LOADING_PORTS_BY_ID: dict[str, LoadingPort] = {p.id: p for p in LOADING_PORTS}


# ── Vessel classes ────────────────────────────────────────────────────────────

VESSEL_SPECS: dict[str, VesselSpec] = {
    "Handysize": VesselSpec(
        "Handysize", 28_000, 40_000, 190, 28, 10.0, 7.5, 14.0, "#22c55e",
        "Smallest bulk carrier. Fits virtually all East Coast ports including Gopalpur and Haldia.",
    ),
    "Supramax": VesselSpec(
        "Supramax", 50_000, 60_000, 200, 32, 12.8, 9.0, 13.5, "#3b82f6",
        "Workhorse of bulk trade. Good fit for Paradip, Dhamra, Gangavaram. Tight on Haldia.",
    ),
    "Panamax": VesselSpec(
        "Panamax", 65_000, 80_000, 229, 32.3, 14.0, 9.5, 13.0, "#f59e0b",
        "Constrained at Haldia and Gopalpur. May require partial lighterage at Sagar/Sandheads.",
    ),
    "Capesize": VesselSpec(
        "Capesize", 100_000, 180_000, 300, 50, 17.5, 11.5, 14.5, "#ef4444",
        "Largest class. Only Gangavaram and Vizag deep-water capable. Lighterage required for Haldia.",
    ),
}


# ── Bridge to the berth table ─────────────────────────────────────────────────
# berths.csv keys ports by name; this module keys them by slug. One map, stated
# once, rather than a string comparison scattered through the routers.

BERTH_PORT_BY_ID: dict[str, str] = {
    "paradip": "Paradip",
    "vizag": "Visakhapatnam",
    "gangavaram": "Gangavaram",
    "gopalpur": "Gopalpur",
    "dhamra": "Dhamra",
    "haldia": "Haldia",
    # An anchorage, not a berth. It appears in lighterage_nodes.csv and in the
    # congestion feed, never in berths.csv.
    "sagar-sandheads": "Sandheads",
}

ID_BY_BERTH_PORT: dict[str, str] = {v: k for k, v in BERTH_PORT_BY_ID.items()}


def berth_port_name(port_id: str) -> str:
    return BERTH_PORT_BY_ID.get(port_id, port_id)


def port_id_for(berth_port: str) -> str:
    return ID_BY_BERTH_PORT.get(berth_port, berth_port.lower())


def resolve_port_key(value: str) -> tuple[str, str]:
    """Accept either a slug or a berth-table name. Returns (port_id, berth_port)."""
    if value in BERTH_PORT_BY_ID:
        return value, BERTH_PORT_BY_ID[value]
    if value in ID_BY_BERTH_PORT:
        return ID_BY_BERTH_PORT[value], value
    lowered = value.strip().lower()
    for pid, name in BERTH_PORT_BY_ID.items():
        if lowered in (pid, name.lower()):
            return pid, name
    return lowered, value


def port_status(port: DischargePort, laden_draft_m: float, loa_m: float) -> str:
    """Available, constrained or blocked for a given vessel geometry."""
    if laden_draft_m > port.current_draft_m or loa_m > port.max_loa_m:
        return "blocked"
    margin = port.current_draft_m - laden_draft_m
    if margin < 1.0 or port.berths_available == 0 or port.congestion_level == "high":
        return "constrained"
    return "available"
