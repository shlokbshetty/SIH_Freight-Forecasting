"""Compatibility surface for the Evaluate page.

The evaluator branch shipped its own FastAPI service with POST /api/evaluate and
a flat port catalogue. That service has been retired in favour of this one, but
its React page is good and there is no reason to throw it away with the backend
it happened to be written against.

So these two routes answer in the shape that page already expects, computed by
the costing engine in app/costing.py. The page needed one import path changed
and nothing else.

Codes here are the evaluator's own vocabulary (PPA, HAY_POINT, PANAMAX). They
are translated to this service's port ids and vessel classes at the boundary and
nowhere else, so the rest of the backend never learns a second naming scheme.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import costing
from app.deps import AppState, get_state, stale_sources, utcnow
from app.rates import build_rate_curve
from app.reference import DISCHARGE_PORTS, LOADING_PORTS, VESSEL_SPECS
from app.schemas import EvaluateRequest
from data.ports import schema as berth_schema

router = APIRouter(prefix="/api", tags=["evaluate"])

#: Evaluator port code -> this service's port id.
CODE_TO_PORT: dict[str, str] = {
    # Indian East Coast discharge ports
    "PPA": "paradip",
    "VIZAG": "vizag",
    "GANGAVARAM": "gangavaram",
    "GOPALPUR": "gopalpur",
    "DHAMRA": "dhamra",
    "SAGAR_SANDHEADS": "sagar-sandheads",
    "HALDIA": "haldia",
    # Load ports
    "HAY_POINT": "abbot-point",
    "NEWCASTLE": "newcastle",
    "TABONEO": "kalimantan",
    "BANJARMASIN": "balikpapan",
    "MAPUTO": "beira",
    "BEIRA_NACALA": "nacala",
    "NORFOLK": "hampton-roads",
    "BALTIMORE": "hampton-roads",
}

PORT_TO_CODE: dict[str, str] = {}
for _code, _pid in CODE_TO_PORT.items():
    PORT_TO_CODE.setdefault(_pid, _code)

VESSEL_BY_CODE: dict[str, str] = {
    "HANDYSIZE": "Handysize",
    "SUPRAMAX": "Supramax",
    "PANAMAX": "Panamax",
    "CAPESIZE": "Capesize",
}

#: The evaluator reported an 80% band as p10/p90.
P10_Z = 1.2816


@router.get("/ports/catalog")
def ports_catalog() -> list[dict]:
    """Flat port list in the evaluator's shape.

    Deliberately a separate path from /api/ports, which returns the berth-level
    payload the rest of this dashboard needs. Two consumers, two shapes, one set
    of underlying data.
    """
    out: list[dict] = []

    for port in DISCHARGE_PORTS:
        berths = berth_schema.berths_for_port(port.name) or berth_schema.berths_for_port(
            {"vizag": "Visakhapatnam"}.get(port.id, port.name)
        )
        deepest = max((b.draft_max_m for b in berths), default=port.current_draft_m)
        out.append({
            "code": PORT_TO_CODE.get(port.id, port.id.upper()),
            "name": port.name,
            "country": "India",
            "is_indian_hub": True,
            "max_draft": round(deepest, 2),
            "max_loa": port.max_loa_m,
            "max_beam": round(port.max_loa_m / 6.5, 1),
            "discharge_rate": float(port.cargo_rate_tpd),
            "load_rate": 0.0,
            "is_anchorage": port.lighterage_required or not berths,
            "latitude": port.lat,
            "longitude": port.lng,
        })

    for load in LOADING_PORTS:
        terms = costing.LOAD_PORT_TERMS.get(load.id, costing.DEFAULT_LOAD_TERMS)
        out.append({
            "code": PORT_TO_CODE.get(load.id, load.id.upper().replace("-", "_")),
            "name": load.name,
            "country": load.country,
            "is_indian_hub": False,
            "max_draft": 18.5,
            "max_loa": 330.0,
            "max_beam": 55.0,
            "discharge_rate": 0.0,
            "load_rate": float(terms[2]),
            "is_anchorage": False,
            "latitude": load.lat,
            "longitude": load.lng,
        })

    return out


@router.post("/evaluate")
def post_evaluate(req: EvaluateRequest, state: AppState = Depends(get_state)) -> dict:
    """Spot versus CVC, in the evaluator page's response shape."""
    vessel_class = VESSEL_BY_CODE.get(req.vessel_code.upper())
    if vessel_class is None:
        raise HTTPException(400, f"unknown vessel code {req.vessel_code!r}")

    origin = CODE_TO_PORT.get(req.origin_code.upper())
    destination = CODE_TO_PORT.get(req.destination_code.upper())
    if origin is None or destination is None:
        raise HTTPException(400, "unknown origin or destination code")

    curve = build_rate_curve(state, vessel_class, steps=req.num_voyages * 90 + 30)
    resolution = costing.plan_call(destination, "thermal_coal", vessel_class, req.cargo_tonnage)
    call = costing.call_economics(resolution)
    port = costing.DISCHARGE_PORTS_BY_ID[destination]
    profile = costing.build_profile(origin, port, vessel_class, req.cargo_tonnage, call)

    departures = [round(i * profile.round_trip_days) for i in range(req.num_voyages)]
    rates = [curve.at(d)[0] for d in departures]
    sds = [curve.at(d)[1] for d in departures]

    from data import cache  # noqa: PLC0415 - avoids a router-level import cycle

    row = cache.latest_observation(state.conn, "bunker.vlsfo.singapore")
    bunker = float(row["value"]) if row else costing.BUNKER_BASIS_USD

    result = costing.evaluate(
        load_port_id=origin,
        discharge_port_id=destination,
        vessel_class=vessel_class,
        cargo_tonnes=req.cargo_tonnage,
        num_voyages=req.num_voyages,
        bunker_price_usd=bunker,
        demurrage_usd_per_day=costing.DEFAULT_DEMURRAGE_USD_PER_DAY,
        cvc_discount_pct=req.cvc_discount_pct,
        market_rate_usd_per_t=curve.market_rate,
        voyage_rates=list(rates),
        voyage_rate_sd=list(sds),
        commodity="thermal_coal",
    )

    usd = costing.USD_INR
    spot_usd = result["spot_total_cr"] * costing.CRORE / usd
    cvc_usd = result["cvc_total_cr"] * costing.CRORE / usd

    p10 = [round(r - P10_Z * sd, 3) for r, sd in zip(rates, sds)]
    p90 = [round(r + P10_Z * sd, 3) for r, sd in zip(rates, sds)]
    non_freight_usd = spot_usd - sum(rates) * req.cargo_tonnage

    plan = resolution.lighterage
    return {
        "cargo_tonnage": req.cargo_tonnage,
        "num_voyages": req.num_voyages,
        "cvc_discount_pct": req.cvc_discount_pct,
        "is_cvc_favorable": result["delta_cr"] >= 0,
        "locked_cvc_rate": result["locked_rate_usd_per_t"],
        "average_spot_rate": result["forecast_avg_usd_per_t"],
        "spot_total_usd": round(spot_usd, 2),
        "cvc_total_usd": round(cvc_usd, 2),
        "base_case_delta_usd": round(spot_usd - cvc_usd, 2),
        "base_case_delta_inr": round((spot_usd - cvc_usd) * usd, 2),
        "base_case_delta_cr": result["delta_cr"],
        "breakeven_spot_rate": result["break_even_usd_per_t"],
        "breakeven_probability_pct": round(result["prob_spot_wins"] * 100, 2),
        "headline_summary": result["headline"],
        "p10_spot_total_usd": round(sum(p10) * req.cargo_tonnage + non_freight_usd, 2),
        "p90_spot_total_usd": round(sum(p90) * req.cargo_tonnage + non_freight_usd, 2),
        "p10_rates": p10,
        "p50_rates": [round(r, 3) for r in rates],
        "p90_rates": p90,
        "voyages": [
            {
                "voyage_number": v["index"],
                "spot_rate": v["rate_usd_per_t"],
                "spot_cost_usd": round(v["spot_cr"] * costing.CRORE / usd, 2),
                "cvc_cost_usd": round(v["cvc_cr"] * costing.CRORE / usd, 2),
            }
            for v in result["voyages"]
        ],
        "lighterage_plan": {
            "is_required": plan is not None,
            "location": plan.node_name if plan else None,
            # How much deeper she floats than the berth can take. The plan's
            # resulting draft is what she sails at once the barges are done.
            "excess_draft": round(resolution.vessel_draft_m - plan.resulting_draft_m, 2) if plan else 0.0,
            "lightered_tonnage": round(plan.tonnes_to_lighten, 1) if plan else 0.0,
            "retained_tonnage": round(req.cargo_tonnage - plan.tonnes_to_lighten, 1) if plan else req.cargo_tonnage,
            "lighterage_cost": round(plan.cost_usd, 2) if plan else 0.0,
            "time_penalty_days": round(plan.added_days, 2) if plan else 0.0,
            "warning_message": plan.narrative if plan else (
                result["blocked_reason"] or None
            ),
        },
        "berth": result.get("berth"),
        "as_of": utcnow(),
        "sources_stale": stale_sources(state.conn),
    }
