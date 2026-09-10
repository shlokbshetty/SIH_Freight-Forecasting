"""Berth resolution.

The cases here are the ones a chartering desk would actually get wrong, and the
ones a single draft-per-port table gets wrong by construction.
"""

from __future__ import annotations

import pytest

from app.reference import VESSEL_SPECS
from data.ports import schema
from data.ports.resolver import Outcome, laden_draft_at_class, resolve_berth


def resolve_class(port: str, commodity: str, vessel_class: str, tonnes: float):
    spec = VESSEL_SPECS[vessel_class]
    return resolve_berth(
        port, commodity, laden_draft_at_class(vessel_class, tonnes), tonnes,
        loa_m=spec.loa_m, beam_m=spec.beam_m,
    )


# ── The data itself ───────────────────────────────────────────────────────────

def test_every_berth_carries_provenance():
    """The whole point of the berth table is that each number is attributable."""
    for berth in schema.load_berths():
        assert berth.source_url.startswith("http"), berth.berth_id
        assert berth.source_date, berth.berth_id


def test_berth_ids_are_unique():
    ids = [b.berth_id for b in schema.load_berths()]
    assert len(ids) == len(set(ids))


def test_anchorages_are_not_berths():
    """Modelling an anchorage as a berth would let the resolver accept a vessel
    somewhere she cannot discharge."""
    berth_ports = {b.port for b in schema.load_berths()}
    assert "Sandheads" not in berth_ports
    assert "Sagar / Sandheads" not in berth_ports
    assert {n.node_id for n in schema.load_lighterage_nodes()} == {"SND-01", "SGR-01"}


def test_tide_allowance_is_additive_not_absolute():
    for berth in schema.load_berths():
        assert berth.draft_max_on_tide_m > berth.draft_max_m


# ── Vizag, which is two basins in one table ───────────────────────────────────

def test_vizag_capesize_iron_ore_goes_to_the_outer_harbour():
    r = resolve_class("Visakhapatnam", "iron_ore", "Capesize", 160_000)
    assert r.outcome is Outcome.ACCEPT_ALL_TIDE
    assert r.berth.berth_id.startswith("VZG-OH")


def test_vizag_supramax_coal_goes_to_the_inner_harbour():
    """A Supramax parcel must not tie up an eighteen-metre Capesize quay."""
    r = resolve_class("Visakhapatnam", "thermal_coal", "Supramax", 55_000)
    assert r.outcome is Outcome.ACCEPT_ALL_TIDE
    assert r.berth.berth_id.startswith("VZG-IH")


def test_vizag_fertiliser_never_reaches_the_outer_harbour():
    r = resolve_class("Visakhapatnam", "fertiliser", "Handysize", 35_000)
    assert r.berth.berth_id.startswith("VZG-IH")


# ── Haldia, which is the lighterage case ──────────────────────────────────────

def test_haldia_handysize_berths_on_the_tide():
    r = resolve_class("Haldia", "thermal_coal", "Handysize", 30_000)
    assert r.outcome is Outcome.ACCEPT_HIGH_TIDE_ONLY


def test_haldia_supramax_rejects_but_returns_a_costed_lighterage_plan():
    r = resolve_class("Haldia", "thermal_coal", "Supramax", 55_000)
    assert r.outcome is Outcome.REJECT
    plan = r.lighterage
    assert plan is not None, "a rejection at Haldia must come back with a route, not a bare no"
    assert plan.tonnes_to_lighten > 0
    assert plan.cost_usd > 0
    assert plan.added_days > 0
    assert plan.resulting_draft_m < r.vessel_draft_m
    assert plan.onward_berth_id is not None


def test_haldia_capesize_is_blocked_on_length_not_draft():
    """Length cannot be lightered away, so the reason must say so. Reporting
    draft would send someone looking for a tide that was never going to help."""
    r = resolve_class("Haldia", "thermal_coal", "Capesize", 160_000)
    assert r.outcome is Outcome.REJECT
    assert "LOA" in r.reason
    assert r.lighterage is None


# ── General behaviour ─────────────────────────────────────────────────────────

def test_commodity_gates_before_anything_else():
    r = resolve_class("Dhamra", "grain", "Panamax", 40_000)
    assert r.outcome is Outcome.REJECT
    assert "grain" in r.reason


def test_part_cargo_can_clear_a_berth_a_full_cargo_cannot():
    """A part cargo floats higher. This is the difference between a tide-bound
    call and an all-tide one, and it is why tonnage belongs in the signature."""
    full = resolve_class("Gopalpur", "thermal_coal", "Handysize", 40_000)
    part = resolve_class("Gopalpur", "thermal_coal", "Handysize", 20_000)
    assert part.vessel_draft_m < full.vessel_draft_m
    assert part.outcome is Outcome.ACCEPT_ALL_TIDE


def test_resolver_reports_every_berth_it_considered():
    r = resolve_class("Paradip", "thermal_coal", "Supramax", 55_000)
    assert len(r.checks) == len(schema.berths_for_port("Paradip"))
    assert all(c.source_url for c in r.checks)


def test_unknown_port_rejects_without_raising():
    r = resolve_berth("Rotterdam", "thermal_coal", 12.0, 50_000)
    assert r.outcome is Outcome.REJECT
    assert r.berth is None


@pytest.mark.parametrize("commodity", ["Coal", "coal", "THERMAL COAL", "thermal-coal"])
def test_commodity_aliases_resolve(commodity):
    assert schema.normalise_commodity(commodity) == "thermal_coal"
