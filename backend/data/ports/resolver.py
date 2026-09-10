"""Berth resolution.

``resolve_berth`` answers the question a chartering desk actually asks: given
this cargo into this port on this ship, where does it go alongside, and is the
answer "yes", "yes but only on the tide", or "no"?

The three outcomes are commercially distinct and are kept distinct:

``ACCEPT_ALL_TIDE``        Berths on arrival. No tidal waiting.
``ACCEPT_HIGH_TIDE_ONLY``  Fits only inside a high-water window. Workable, but
                           it buys waiting days, and a fixture priced as though
                           it were all-tide is priced wrong.
``REJECT``                 Cannot berth as loaded. Where the port has a
                           lighterage anchorage, a costed route via that
                           anchorage comes back with the rejection instead of a
                           bare no.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from app.reference import VESSEL_SPECS
from data.ports.schema import (
    Berth,
    LighterageNode,
    berths_for_port,
    nodes_for_port,
    normalise_commodity,
)

#: Water held between keel and seabed. Ports publish permissible draft, which
#: already allows for it, so this is the operator's own working margin on top.
UKC_MARGIN_M = 0.4

#: Tonnes per centimetre immersion. Converts a draft shortfall straight into
#: the tonnage that has to come off before the ship can enter.
TONNES_PER_CM = {"Handysize": 38, "Supramax": 52, "Panamax": 66, "Capesize": 108}

#: Days to bring barges alongside before any cargo moves.
LIGHTERAGE_MOBILISATION_DAYS = 0.75

#: Berth allocation bands, in metres of draft headroom.
#:
#: A port does not simply give a ship the deepest free berth, nor the tightest
#: one that technically fits. It wants her on a berth that suits her: enough
#: water to work without watching the gauge, without tying up a Capesize quay
#: for a Supramax parcel. Anything under MIN_COMFORT is workable but leaves no
#: margin for a swell or a loading error; anything over GOOD_FIT_MAX is a berth
#: someone bigger wants.
MIN_COMFORT_HEADROOM_M = 0.5
GOOD_FIT_MAX_HEADROOM_M = 2.5


class Outcome(str, Enum):
    ACCEPT_ALL_TIDE = "ACCEPT_ALL_TIDE"
    ACCEPT_HIGH_TIDE_ONLY = "ACCEPT_HIGH_TIDE_ONLY"
    REJECT = "REJECT"


@dataclass
class BerthCheck:
    """One berth's verdict, kept even when it fails so the UI can show why."""

    berth_id: str
    berth_name: str
    outcome: Outcome
    reason: str
    draft_headroom_m: float | None = None
    source_url: str = ""
    source_date: str = ""

    def to_dict(self) -> dict:
        return {
            "berth_id": self.berth_id,
            "berth_name": self.berth_name,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "draft_headroom_m": self.draft_headroom_m,
            "provenance": {"source_url": self.source_url, "source_date": self.source_date},
        }


@dataclass
class LighteragePlan:
    node_id: str
    node_name: str
    tonnes_to_lighten: float
    barge_trips: int
    added_days: float
    cost_usd: float
    resulting_draft_m: float
    onward_berth_id: str | None
    onward_outcome: Outcome
    narrative: str
    source_url: str = ""
    source_date: str = ""

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "tonnes_to_lighten": round(self.tonnes_to_lighten, 1),
            "barge_trips": self.barge_trips,
            "added_days": round(self.added_days, 2),
            "cost_usd": round(self.cost_usd, 2),
            "resulting_draft_m": round(self.resulting_draft_m, 2),
            "onward_berth_id": self.onward_berth_id,
            "onward_outcome": self.onward_outcome.value,
            "narrative": self.narrative,
            "provenance": {"source_url": self.source_url, "source_date": self.source_date},
        }


@dataclass
class BerthResolution:
    port: str
    commodity: str
    vessel_draft_m: float
    tonnage: float
    outcome: Outcome
    berth: Berth | None
    reason: str
    checks: list[BerthCheck] = field(default_factory=list)
    lighterage: LighteragePlan | None = None
    turnaround_days: float | None = None

    def to_dict(self) -> dict:
        return {
            "port": self.port,
            "commodity": self.commodity,
            "vessel_draft_m": round(self.vessel_draft_m, 2),
            "tonnage": int(self.tonnage),
            "outcome": self.outcome.value,
            "reason": self.reason,
            "berth": self.berth.to_dict() if self.berth else None,
            "turnaround_days": round(self.turnaround_days, 2) if self.turnaround_days else None,
            "lighterage": self.lighterage.to_dict() if self.lighterage else None,
            "considered": [c.to_dict() for c in self.checks],
        }


# ── Vessel geometry ───────────────────────────────────────────────────────────

def laden_draft_at_class(vessel_class: str, cargo_tonnes: float) -> float:
    """Draft a ship of this class floats at on this parcel.

    A part cargo floats higher and may clear a berth a full cargo cannot, which
    is the difference between a tide-bound call and an all-tide one.
    """
    spec = VESSEL_SPECS[vessel_class]
    utilisation = max(0.0, min(1.0, cargo_tonnes / spec.dwt_max))
    return spec.ballast_draft_m + (spec.laden_draft_m - spec.ballast_draft_m) * utilisation


def infer_vessel_class(tonnage: float) -> str:
    """Smallest class that can lift the parcel."""
    for name in ("Handysize", "Supramax", "Panamax", "Capesize"):
        if tonnage <= VESSEL_SPECS[name].dwt_max:
            return name
    return "Capesize"


def _geometry(tonnage: float, loa_m: float | None, beam_m: float | None) -> tuple[float, float, str]:
    cls = infer_vessel_class(tonnage)
    spec = VESSEL_SPECS[cls]
    return (loa_m or spec.loa_m), (beam_m or spec.beam_m), cls


# ── Resolution ────────────────────────────────────────────────────────────────

def _check(berth: Berth, commodity: str, draft: float, loa: float, beam: float) -> BerthCheck:
    base = dict(
        berth_id=berth.berth_id,
        berth_name=berth.berth_name,
        source_url=berth.source_url,
        source_date=berth.source_date,
    )

    if not berth.handles(commodity):
        return BerthCheck(
            outcome=Outcome.REJECT,
            reason=f"Not equipped for {commodity}; handles {', '.join(berth.commodities)}",
            **base,
        )
    if loa > berth.loa_max_m:
        return BerthCheck(
            outcome=Outcome.REJECT,
            reason=f"LOA {loa:.0f} m over the {berth.loa_max_m:.0f} m limit",
            **base,
        )
    if beam > berth.beam_max_m:
        return BerthCheck(
            outcome=Outcome.REJECT,
            reason=f"Beam {beam:.1f} m over the {berth.beam_max_m:.1f} m limit",
            **base,
        )

    required = draft + UKC_MARGIN_M
    if required <= berth.draft_max_m:
        return BerthCheck(
            outcome=Outcome.ACCEPT_ALL_TIDE,
            reason=(
                f"{draft:.1f} m plus {UKC_MARGIN_M:.1f} m clearance inside the "
                f"{berth.draft_max_m:.1f} m all-tide draft"
            ),
            draft_headroom_m=round(berth.draft_max_m - required, 2),
            **base,
        )
    if required <= berth.draft_max_on_tide_m:
        return BerthCheck(
            outcome=Outcome.ACCEPT_HIGH_TIDE_ONLY,
            reason=(
                f"{draft:.1f} m needs {required - berth.draft_max_m:.1f} m of tide over the "
                f"{berth.draft_max_m:.1f} m all-tide draft; berth carries "
                f"{berth.tide_required_m:.1f} m on high water"
            ),
            draft_headroom_m=round(berth.draft_max_on_tide_m - required, 2),
            **base,
        )
    return BerthCheck(
        outcome=Outcome.REJECT,
        reason=(
            f"{draft:.1f} m exceeds {berth.draft_max_on_tide_m:.1f} m even on high water "
            f"by {required - berth.draft_max_on_tide_m:.1f} m"
        ),
        draft_headroom_m=round(berth.draft_max_on_tide_m - required, 2),
        **base,
    )


_RANK = {Outcome.ACCEPT_ALL_TIDE: 0, Outcome.ACCEPT_HIGH_TIDE_ONLY: 1, Outcome.REJECT: 2}


def _fit_band(headroom_m: float | None) -> int:
    """0 well matched, 1 more berth than she needs, 2 workable but tight."""
    if headroom_m is None:
        return 2
    if headroom_m < MIN_COMFORT_HEADROOM_M:
        return 2
    if headroom_m > GOOD_FIT_MAX_HEADROOM_M:
        return 1
    return 0


def resolve_berth(
    port: str,
    commodity: str,
    vessel_draft: float,
    tonnage: float,
    *,
    loa_m: float | None = None,
    beam_m: float | None = None,
    allow_lighterage: bool = True,
) -> BerthResolution:
    """Best eligible berth for this cargo and ship, or why there is none.

    ``loa_m`` and ``beam_m`` are inferred from the parcel size when not given,
    so the four-argument call in the brief works, and a caller who knows the
    actual ship can pass its real dimensions.
    """
    commodity = normalise_commodity(commodity)
    loa, beam, _cls = _geometry(tonnage, loa_m, beam_m)
    berths = berths_for_port(port)

    if not berths:
        return BerthResolution(
            port=port, commodity=commodity, vessel_draft_m=vessel_draft, tonnage=tonnage,
            outcome=Outcome.REJECT, berth=None,
            reason=f"No berth data for {port!r}",
        )

    checks = [_check(b, commodity, vessel_draft, loa, beam) for b in berths]
    by_id = {b.berth_id: b for b in berths}

    eligible = [c for c in checks if c.outcome is not Outcome.REJECT]
    # Tide verdict first, then how well the berth suits her, then how fast it
    # works her, then whether it is mechanised.
    eligible.sort(
        key=lambda c: (
            _RANK[c.outcome],
            _fit_band(c.draft_headroom_m),
            -by_id[c.berth_id].discharge_rate_tpd,
            not by_id[c.berth_id].mechanised,
        )
    )

    if eligible:
        best = eligible[0]
        berth = by_id[best.berth_id]
        turnaround = tonnage / max(1, berth.discharge_rate_tpd)
        if best.outcome is Outcome.ACCEPT_HIGH_TIDE_ONLY:
            # Tide-bound arrivals wait for water. Half a spring cycle is the
            # conventional planning allowance.
            turnaround += 0.5
        if berth.night_restricted:
            turnaround *= 1.15
        return BerthResolution(
            port=port, commodity=commodity, vessel_draft_m=vessel_draft, tonnage=tonnage,
            outcome=best.outcome, berth=berth, reason=best.reason,
            checks=checks, turnaround_days=turnaround,
        )

    # Nothing takes her as loaded.
    plan = None
    if allow_lighterage:
        plan = _plan_lighterage(port, commodity, vessel_draft, tonnage, loa, beam, checks)

    reason = _rejection_reason(port, commodity, vessel_draft, loa, beam, checks, by_id)

    return BerthResolution(
        port=port, commodity=commodity, vessel_draft_m=vessel_draft, tonnage=tonnage,
        outcome=Outcome.REJECT, berth=None, reason=reason, checks=checks, lighterage=plan,
    )


def _rejection_reason(
    port: str, commodity: str, vessel_draft: float, loa: float, beam: float,
    checks: list[BerthCheck], by_id: dict[str, Berth],
) -> str:
    """Name the constraint that actually blocks her, in that order of finality.

    Commodity first, because no tide or lightening fixes a berth that has no
    grab for the cargo. Then length and beam, which cannot be lightered away.
    Draft comes last, because it is the only one cargo can be taken off to fix.
    """
    handling = [by_id[c.berth_id] for c in checks if by_id[c.berth_id].handles(commodity)]
    if not handling:
        return f"No berth at {port} handles {commodity}"

    fits_geometry = [b for b in handling if loa <= b.loa_max_m and beam <= b.beam_max_m]
    if not fits_geometry:
        longest = max(b.loa_max_m for b in handling)
        widest = max(b.beam_max_m for b in handling)
        if loa > longest:
            return (
                f"LOA {loa:.0f} m exceeds every {commodity} berth at {port}; "
                f"longest takes {longest:.0f} m. Length cannot be lightered away."
            )
        return (
            f"Beam {beam:.1f} m exceeds every {commodity} berth at {port}; "
            f"widest takes {widest:.1f} m."
        )

    deepest = max(b.draft_max_on_tide_m for b in fits_geometry)
    return (
        f"{vessel_draft:.1f} m draft exceeds the deepest eligible {commodity} berth at "
        f"{port} ({deepest:.1f} m on high water)"
    )


# ── Lighterage ────────────────────────────────────────────────────────────────

def _plan_lighterage(
    port: str, commodity: str, vessel_draft: float, tonnage: float,
    loa: float, beam: float, checks: list[BerthCheck],
) -> LighteragePlan | None:
    """Cost the route via an anchorage when the ship cannot enter as loaded.

    This is what Haldia needs. Anything over the dock's draft lightens at
    Sandheads or Sagar, and the answer that comes back is a number of days and
    dollars, not simply "no".
    """
    nodes = nodes_for_port(port)
    if not nodes:
        return None

    berths = {b.berth_id: b for b in berths_for_port(port)}
    eligible = [b for b in berths.values() if b.handles(commodity) and loa <= b.loa_max_m and beam <= b.beam_max_m]
    if not eligible:
        return None

    # Lighten to the deepest berth that will then take her, preferring all tide.
    target = max(eligible, key=lambda b: b.draft_max_m)
    target_draft = target.draft_max_m - UKC_MARGIN_M
    onward_outcome = Outcome.ACCEPT_ALL_TIDE
    if target_draft <= 0:
        return None

    cls = infer_vessel_class(tonnage)
    tpc = TONNES_PER_CM[cls]
    shortfall_m = vessel_draft - target_draft
    tonnes = min(tonnage * 0.9, max(0.0, shortfall_m) * 100 * tpc)
    if tonnes <= 0:
        return None

    node = min(
        (n for n in nodes if n.max_draft_m + 0.001 >= vessel_draft),
        key=lambda n: n.transfer_cost_usd_per_t,
        default=None,
    )
    if node is None:
        # No anchorage deep enough to lie at while lightening.
        deepest = max(nodes, key=lambda n: n.max_draft_m)
        return LighteragePlan(
            node_id=deepest.node_id, node_name=deepest.node_name,
            tonnes_to_lighten=tonnes, barge_trips=0, added_days=0.0, cost_usd=0.0,
            resulting_draft_m=vessel_draft,
            onward_berth_id=None, onward_outcome=Outcome.REJECT,
            narrative=(
                f"No anchorage serving {port} can take {vessel_draft:.1f} m; "
                f"deepest is {deepest.node_name} at {deepest.max_draft_m:.1f} m."
            ),
            source_url=deepest.source_url, source_date=deepest.source_date,
        )

    trips = math.ceil(tonnes / max(1, node.barge_capacity_t))
    added_days = LIGHTERAGE_MOBILISATION_DAYS + tonnes / max(1, node.lighterage_rate_tpd)
    cost = tonnes * node.transfer_cost_usd_per_t + node.mobilisation_usd
    resulting = vessel_draft - (tonnes / tpc) / 100

    return LighteragePlan(
        node_id=node.node_id, node_name=node.node_name,
        tonnes_to_lighten=tonnes, barge_trips=trips, added_days=added_days,
        cost_usd=cost, resulting_draft_m=resulting,
        onward_berth_id=target.berth_id, onward_outcome=onward_outcome,
        narrative=(
            f"{cls} arrives at {vessel_draft:.1f} m against {target.berth_name}'s "
            f"{target.draft_max_m:.1f} m. Lighten {tonnes:,.0f} T at {node.node_name} "
            f"over {trips} barge trip{'s' if trips != 1 else ''}, sail at "
            f"{resulting:.1f} m, then berth all tide."
        ),
        source_url=node.source_url, source_date=node.source_date,
    )
