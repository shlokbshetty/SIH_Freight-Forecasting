"""GET /api/ports - berth-level reference data with per-row provenance."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_conn, stale_sources, utcnow
from app.reference import (
    DISCHARGE_PORTS,
    LOADING_PORTS,
    VESSEL_SPECS,
    berth_port_name,
    resolve_port_key,
)
from data import cache
from data.ports import schema as berth_schema

router = APIRouter(prefix="/api", tags=["reference"])


def _live(conn: sqlite3.Connection, berth_port: str) -> dict:
    wait = cache.latest_observation(conn, f"congestion.{berth_port}.wait_days")
    anchored = cache.latest_observation(conn, f"congestion.{berth_port}.vessels_at_anchor")
    return {
        "wait_days": round(wait["value"], 2) if wait else None,
        "vessels_at_anchor": int(anchored["value"]) if anchored else None,
        "observed_at": (wait or anchored)["timestamp"] if (wait or anchored) else None,
        "source": (wait or anchored)["source"] if (wait or anchored) else None,
    }


@router.get("/ports")
def get_ports(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    """Every discharge port, its berths, and where each number came from.

    The flat one-draft-per-port table is gone. A port publishes a headline
    figure, but ships berth at berths, and Paradip's iron ore quay and its
    central quays are five metres apart.
    """
    ports = []
    for port in DISCHARGE_PORTS:
        name = berth_port_name(port.id)
        berths = berth_schema.berths_for_port(name)
        nodes = berth_schema.nodes_for_port(name)
        entry = port.to_dict()
        entry["berth_port_name"] = name
        entry["is_anchorage"] = not berths and bool(
            berth_schema.nodes_for_port(name) or port.lighterage_required
        )
        entry["berths"] = [b.to_dict() for b in berths]
        entry["lighterage_nodes"] = [n.to_dict() for n in nodes]
        entry["deepest_berth_m"] = max((b.draft_max_m for b in berths), default=None)
        entry["deepest_on_tide_m"] = max((b.draft_max_on_tide_m for b in berths), default=None)
        entry["live"] = _live(conn, name)
        ports.append(entry)

    return {
        "as_of": utcnow(),
        "sources_stale": stale_sources(conn),
        "provenance": berth_schema.provenance_summary(),
        "commodities": list(berth_schema.COMMODITIES),
        "discharge_ports": ports,
        "loading_ports": [p.to_dict() for p in LOADING_PORTS],
        "vessel_specs": {k: v.to_dict() for k, v in VESSEL_SPECS.items()},
    }


@router.get("/ports/{port_key}/berths")
def get_berths(port_key: str) -> dict:
    """Berths for one port. Every row carries its own source URL and date."""
    _pid, name = resolve_port_key(port_key)
    berths = berth_schema.berths_for_port(name)
    nodes = berth_schema.nodes_for_port(name)
    if not berths and not nodes:
        raise HTTPException(404, f"no berth or anchorage data for {port_key!r}")
    return {
        "port": name,
        "berths": [b.to_dict() for b in berths],
        "lighterage_nodes": [n.to_dict() for n in nodes],
        "provenance": berth_schema.provenance_summary(),
    }
