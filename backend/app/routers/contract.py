"""POST /api/contract - spot versus consecutive voyage charter."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import costing
from app.deps import AppState, get_state, stale_sources, utcnow
from app.rates import build_rate_curve
from app.reference import DISCHARGE_PORTS_BY_ID, berth_port_name
from app.schemas import ContractRequest, ContractResponse, MultiPortRequest
from data import cache

router = APIRouter(prefix="/api", tags=["contract"])


@router.post("/contract", response_model=ContractResponse)
def post_contract(req: ContractRequest, state: AppState = Depends(get_state)) -> ContractResponse:
    """Price a multi-voyage programme both ways.

    Each voyage is priced at the projected rate for its own departure, which is
    one round trip after the last, so the comparison reflects where the model
    thinks the market is going rather than where it is today.
    """
    port = DISCHARGE_PORTS_BY_ID.get(req.discharge_port_id) or DISCHARGE_PORTS_BY_ID["paradip"]

    bunker_price = req.bunker_price_usd
    if bunker_price is None:
        row = cache.latest_observation(state.conn, "bunker.vlsfo.singapore")
        bunker_price = float(row["value"]) if row else costing.BUNKER_BASIS_USD

    # Berth waiting comes from the congestion feed where we have it, and from
    # the port's standing congestion level where we do not.
    berth_port = berth_port_name(port.id)
    observed = cache.latest_observation(state.conn, f"congestion.{berth_port}.wait_days")
    observed_wait = float(observed["value"]) if observed else None

    # Resolve the call first: the berth she actually goes to sets the discharge
    # rate, and any lighterage sets the added days, which together fix the
    # round-trip length that the voyage departures are spaced on.
    curve = build_rate_curve(state, req.vessel_class, steps=req.num_voyages * 90 + 30)
    resolution = costing.plan_call(port.id, req.commodity, req.vessel_class, req.cargo_tonnes)
    call = costing.call_economics(resolution)
    profile = costing.build_profile(
        req.load_port_id, port, req.vessel_class, req.cargo_tonnes, call, observed_wait
    )

    departures = [round(i * profile.round_trip_days) for i in range(req.num_voyages)]
    voyage_rates, voyage_sd = [], []
    for day in departures:
        mean, sd = curve.at(day)
        voyage_rates.append(mean)
        voyage_sd.append(sd)

    result = costing.evaluate(
        load_port_id=req.load_port_id,
        discharge_port_id=port.id,
        vessel_class=req.vessel_class,
        cargo_tonnes=req.cargo_tonnes,
        num_voyages=req.num_voyages,
        bunker_price_usd=bunker_price,
        demurrage_usd_per_day=req.demurrage_usd_per_day,
        cvc_discount_pct=req.cvc_discount_pct,
        market_rate_usd_per_t=curve.market_rate,
        voyage_rates=voyage_rates,
        voyage_rate_sd=voyage_sd,
        commodity=req.commodity,
        observed_wait_days=observed_wait,
    )

    return ContractResponse(
        as_of=utcnow(),
        sources_stale=stale_sources(state.conn),
        **result,
    )


@router.post("/contract/multiport")
def post_multiport(req: MultiPortRequest, state: AppState = Depends(get_state)) -> dict:
    """Split one cargo across two discharge ports, or prove it is not worth it.

    Two things can make a split pay. Reach, where a ship too deep for the second
    port arrives there already lightened by the first discharge, and the sea has
    done the lightering for nothing. And cost, where two smaller parcels beat one
    barge bill. The optimiser reports both, and says plainly when neither holds
    and a single call is simply cheaper.
    """
    curve = build_rate_curve(state, req.vessel_class, steps=120)
    rate = req.rate_usd_per_t if req.rate_usd_per_t is not None else curve.market_rate

    bunker = req.bunker_price_usd
    if bunker is None:
        row = cache.latest_observation(state.conn, "bunker.vlsfo.singapore")
        bunker = float(row["value"]) if row else costing.BUNKER_BASIS_USD

    try:
        result = costing.evaluate_multiport(
            load_port_id=req.load_port_id,
            discharge_port_ids=req.discharge_port_ids,
            vessel_class=req.vessel_class,
            total_tonnes=req.total_tonnes,
            commodity=req.commodity,
            rate_usd_per_t=rate,
            bunker_price_usd=bunker,
            demurrage_usd_per_day=req.demurrage_usd_per_day,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    result["as_of"] = utcnow()
    result["sources_stale"] = stale_sources(state.conn)
    return result
