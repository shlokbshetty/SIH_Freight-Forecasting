"""Berth-level port model.

Replaces the single draft-per-port table. A port is not one number: Paradip's
iron ore berth takes seventeen metres while its central quays take twelve, and
picking a ship on the port's headline figure is how vessels end up waiting.

Column semantics, which matter more than the schema itself:

``draft_max_m``      Permissible arrival and sailing draft at **all states of
                     tide**. A vessel inside this can work whenever it arrives.
``tide_required_m``  Additional draft the berth can accept inside a high-water
                     window. Maximum on tide is ``draft_max_m + tide_required_m``.
                     A vessel in that band is workable but tide-bound, which
                     costs waiting days and is a different commercial answer
                     from "yes".
``commodity``        Pipe-separated list. A berth is eligible only for what it
                     is equipped to handle.
``source_url``       Where the figure came from.
``source_date``      When it was compiled. Both travel with every row and are
                     exposed through the API so the UI can show provenance per
                     number rather than per page.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, asdict, field
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

PORTS_DIR = Path(__file__).resolve().parent
BERTHS_CSV = PORTS_DIR / "berths.csv"
LIGHTERAGE_CSV = PORTS_DIR / "lighterage_nodes.csv"

#: Canonical commodity keys used across the berth table and the API.
COMMODITIES = (
    "thermal_coal",
    "coking_coal",
    "iron_ore",
    "bauxite",
    "limestone",
    "fertiliser",
    "grain",
    "general",
)

#: Loose inbound names mapped onto the canonical set, so "Coal" from the UI and
#: "thermal_coal" from a script land in the same place.
COMMODITY_ALIASES = {
    "coal": "thermal_coal",
    "steam coal": "thermal_coal",
    "thermal coal": "thermal_coal",
    "coking coal": "coking_coal",
    "met coal": "coking_coal",
    "metallurgical coal": "coking_coal",
    "iron ore": "iron_ore",
    "ore": "iron_ore",
    "fertilizer": "fertiliser",
    "general cargo": "general",
    "break bulk": "general",
}


def normalise_commodity(value: str) -> str:
    key = (value or "").strip().lower().replace("-", " ")
    if key in COMMODITY_ALIASES:
        return COMMODITY_ALIASES[key]
    underscored = key.replace(" ", "_")
    return underscored if underscored in COMMODITIES else underscored


@dataclass(frozen=True)
class Berth:
    port: str
    berth_id: str
    berth_name: str
    operator: str
    commodities: tuple[str, ...]
    loa_max_m: float
    beam_max_m: float
    draft_max_m: float
    tide_required_m: float
    night_restricted: bool
    discharge_rate_tpd: int
    mechanised: bool
    source_url: str
    source_date: str

    @property
    def draft_max_on_tide_m(self) -> float:
        """Deepest draft the berth can take inside a high-water window."""
        return self.draft_max_m + self.tide_required_m

    def handles(self, commodity: str) -> bool:
        return normalise_commodity(commodity) in self.commodities

    def to_dict(self) -> dict:
        d = asdict(self)
        d["commodities"] = list(self.commodities)
        d["draft_max_on_tide_m"] = round(self.draft_max_on_tide_m, 2)
        d["provenance"] = {"source_url": self.source_url, "source_date": self.source_date}
        return d


@dataclass(frozen=True)
class LighterageNode:
    """An anchorage where cargo comes off into barges.

    Sagar and Sandheads are not berths and are deliberately not in berths.csv.
    Modelling an anchorage as a berth would let the resolver "accept" a vessel
    at a place it cannot discharge.
    """

    node_id: str
    node_name: str
    port_served: str
    lat: float
    lng: float
    max_draft_m: float
    lighterage_rate_tpd: int
    barge_capacity_t: int
    transfer_cost_usd_per_t: float
    mobilisation_usd: float
    source_url: str
    source_date: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["provenance"] = {"source_url": self.source_url, "source_date": self.source_date}
        return d


def _as_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


@lru_cache(maxsize=1)
def load_berths(path: Path | None = None) -> tuple[Berth, ...]:
    src = path or BERTHS_CSV
    berths: list[Berth] = []
    with src.open("r", encoding="utf-8", newline="") as fh:
        for line, row in enumerate(csv.DictReader(fh), start=2):
            try:
                berths.append(
                    Berth(
                        port=row["port"].strip(),
                        berth_id=row["berth_id"].strip(),
                        berth_name=row["berth_name"].strip(),
                        operator=row["operator"].strip(),
                        commodities=tuple(
                            normalise_commodity(c) for c in row["commodity"].split("|") if c.strip()
                        ),
                        loa_max_m=float(row["loa_max_m"]),
                        beam_max_m=float(row["beam_max_m"]),
                        draft_max_m=float(row["draft_max_m"]),
                        tide_required_m=float(row["tide_required_m"]),
                        night_restricted=_as_bool(row["night_restricted"]),
                        discharge_rate_tpd=int(float(row["discharge_rate_tpd"])),
                        mechanised=_as_bool(row["mechanised"]),
                        source_url=row["source_url"].strip(),
                        source_date=row["source_date"].strip(),
                    )
                )
            except (KeyError, ValueError) as exc:
                # One malformed row must not cost us the whole table.
                log.warning("skipping %s line %s: %s", src.name, line, exc)
    if not berths:
        log.error("no berths loaded from %s", src)
    return tuple(berths)


@lru_cache(maxsize=1)
def load_lighterage_nodes(path: Path | None = None) -> tuple[LighterageNode, ...]:
    src = path or LIGHTERAGE_CSV
    nodes: list[LighterageNode] = []
    try:
        with src.open("r", encoding="utf-8", newline="") as fh:
            for line, row in enumerate(csv.DictReader(fh), start=2):
                try:
                    nodes.append(
                        LighterageNode(
                            node_id=row["node_id"].strip(),
                            node_name=row["node_name"].strip(),
                            port_served=row["port_served"].strip(),
                            lat=float(row["lat"]),
                            lng=float(row["lng"]),
                            max_draft_m=float(row["max_draft_m"]),
                            lighterage_rate_tpd=int(float(row["lighterage_rate_tpd"])),
                            barge_capacity_t=int(float(row["barge_capacity_t"])),
                            transfer_cost_usd_per_t=float(row["transfer_cost_usd_per_t"]),
                            mobilisation_usd=float(row["mobilisation_usd"]),
                            source_url=row["source_url"].strip(),
                            source_date=row["source_date"].strip(),
                        )
                    )
                except (KeyError, ValueError) as exc:
                    log.warning("skipping %s line %s: %s", src.name, line, exc)
    except OSError as exc:
        log.warning("no lighterage nodes loaded: %s", exc)
    return tuple(nodes)


def ports() -> list[str]:
    seen: list[str] = []
    for b in load_berths():
        if b.port not in seen:
            seen.append(b.port)
    return seen


def berths_for_port(port: str) -> list[Berth]:
    key = port.strip().lower()
    return [b for b in load_berths() if b.port.lower() == key]


def nodes_for_port(port: str) -> list[LighterageNode]:
    key = port.strip().lower()
    return [n for n in load_lighterage_nodes() if n.port_served.lower() == key]


def provenance_summary() -> dict:
    """Dataset-level provenance, alongside the per-row source on every berth."""
    berths = load_berths()
    dates = sorted({b.source_date for b in berths})
    return {
        "berth_rows": len(berths),
        "ports": ports(),
        "lighterage_nodes": [n.node_id for n in load_lighterage_nodes()],
        "source_dates": dates,
        "sources": sorted({b.source_url for b in berths}),
        "caveat": (
            "Berth dimensions are compiled from public port-authority material and "
            "are indicative. Verify against the operator's current vessel-related "
            "particulars before fixing on them."
        ),
    }
