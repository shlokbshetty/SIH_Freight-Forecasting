"""POST /api/match - which vessel class berths, and where."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import costing
from app.deps import AppState, get_state, stale_sources, utcnow
from app.rates import build_rate_curve
from app.reference import VESSEL_CLASSES, resolve_port_key
from app.schemas import MatchRequest, MatchResponse
from data.ports import schema as berth_schema
from data.ports.resolver import Outcome, resolve_berth

router = APIRouter(prefix="/api", tags=["match"])

#: All-tide beats tide-bound beats no.
_RANK = {
    Outcome.ACCEPT_ALL_TIDE.value: 0,
    Outcome.ACCEPT_HIGH_TIDE_ONLY.value: 1,
    Outcome.REJECT.value: 2,
}


@router.post("/match", response_model=MatchResponse)
def post_match(req: MatchRequest, state: AppState = Depends(get_state)) -> MatchResponse:
    """Run every vessel class through the berth resolver for this cargo.

    The answer is three-valued on purpose. "Berths on arrival" and "berths only
    on the tide" are different fixtures at different prices, and collapsing them
    into a single yes is how tidal waiting ends up unpriced.
    """
    port_id, berth_port = resolve_port_key(req.discharge_port_id)
    if not berth_schema.berths_for_port(berth_port) and not berth_schema.nodes_for_port(berth_port):
        raise HTTPException(404, f"no berth data for {req.discharge_port_id!r}")

    commodity = berth_schema.normalise_commodity(req.commodity)
    recommendations = []

    for cls in VESSEL_CLASSES:
        spec = costing.VESSEL_SPECS[cls]
        draft = req.vessel_draft_m or costing.laden_draft_at(cls, req.cargo_tonnes)

        resolution = resolve_berth(
            berth_port, commodity, draft, req.cargo_tonnes,
            loa_m=spec.loa_m, beam_m=spec.beam_m,
        )

        curve = build_rate_curve(state, cls, steps=90)
        recommendations.append(
            {
                "vessel_class": cls,
                "outcome": resolution.outcome.value,
                "reason": resolution.reason,
                "laden_draft_m": round(draft, 2),
                "berth": resolution.berth.to_dict() if resolution.berth else None,
                "turnaround_days": (
                    round(resolution.turnaround_days, 2) if resolution.turnaround_days else None
                ),
                "estimated_rate_usd_per_t": (
                    round(curve.market_rate, 3) if curve.market_rate > 0 else None
                ),
                "lighterage": resolution.lighterage.to_dict() if resolution.lighterage else None,
                "considered": [c.to_dict() for c in resolution.checks],
            }
        )

    recommendations.sort(
        key=lambda r: (
            _RANK[r["outcome"]],
            r["turnaround_days"] if r["turnaround_days"] is not None else 1e9,
        )
    )

    return MatchResponse(
        discharge_port_id=port_id,
        discharge_port_name=berth_port,
        commodity=commodity,
        cargo_tonnes=req.cargo_tonnes,
        as_of=utcnow(),
        sources_stale=stale_sources(state.conn),
        provenance=berth_schema.provenance_summary(),
        recommendations=recommendations,
    )
