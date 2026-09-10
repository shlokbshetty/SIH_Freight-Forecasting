"""
FastAPI Application — Maritime Freight Forecasting API.

Exposes two endpoints:
  POST /api/evaluate  — Run Spot vs. CVC financial evaluation
  GET  /api/ports     — List all 15 registered ports with metadata
"""

import logging
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from data.ports import ALL_PORTS, get_all_ports, get_port
from data.vessels import VESSEL_CLASSES, get_vessel_class
from engine.feasibility import FeasibilityEngine
from engine.financial_evaluator import FinancialEvaluator

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Maritime Freight Forecasting API",
    description="Spot vs. CVC financial evaluation with ML quantile forecasts",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Singletons ────────────────────────────────────────────────────────────────
_evaluator = FinancialEvaluator()
_feasibility = FeasibilityEngine()

# ── 24-hour port response cache ───────────────────────────────────────────────
_port_cache: Dict[str, Any] = {"data": None, "ts": 0.0}
_PORT_CACHE_TTL = 86400  # seconds


# ── Request / Response schemas ────────────────────────────────────────────────

class EvaluationRequest(BaseModel):
    cargo_tonnage: float = Field(..., gt=0, le=500_000, description="Cargo in metric tons (1,000–500,000)")
    origin_code: str = Field(..., description="Origin port code (e.g. NEWCASTLE)")
    destination_code: str = Field(..., description="Destination port code (e.g. HALDIA)")
    vessel_code: str = Field(..., description="Vessel class code (e.g. PANAMAX)")
    num_voyages: int = Field(4, ge=1, le=12, description="Number of voyages (1–12)")
    cvc_discount_pct: float = Field(5.0, ge=0.0, le=15.0, description="CVC discount % (0–15)")

    @field_validator("cargo_tonnage")
    @classmethod
    def validate_cargo_tonnage(cls, v: float) -> float:
        if v < 1_000:
            raise ValueError("Cargo tonnage must be at least 1,000 MT")
        return v


class LighterageResponse(BaseModel):
    is_required: bool
    location: Optional[str]
    excess_draft: float
    lightered_tonnage: float
    retained_tonnage: float
    lighterage_cost: float
    time_penalty_days: float
    warning_message: Optional[str]


class VoyageBreakdownResponse(BaseModel):
    voyage_number: int
    spot_freight_rate: float
    spot_freight_cost: float
    cvc_freight_rate: float
    cvc_freight_cost: float
    bunker_adj_cost: float
    port_charges: float
    wait_days: float
    demurrage_cost: float
    lighterage_tonnage: float
    lighterage_cost: float
    spot_voyage_total: float
    cvc_voyage_total: float
    voyage_savings: float
    p10_spot_rate: float
    p90_spot_rate: float


class EvaluationResponse(BaseModel):
    # Inputs echoed back
    cargo_tonnage: float
    num_voyages: int
    cvc_discount_pct: float

    # Financial outcomes
    is_cvc_favorable: bool
    locked_cvc_rate: float
    average_spot_rate: float
    spot_total_usd: float
    cvc_total_usd: float
    base_case_delta_usd: float
    base_case_delta_inr: float
    base_case_delta_cr: float

    # Break-even & probability
    breakeven_spot_rate: float
    breakeven_probability_pct: float

    # Headline
    headline_summary: str

    # Confidence totals
    p10_spot_total_usd: float
    p90_spot_total_usd: float

    # Quantile rate arrays (one value per voyage)
    p10_rates: List[float]
    p50_rates: List[float]
    p90_rates: List[float]

    # Voyage breakdown
    voyages: List[VoyageBreakdownResponse]

    # Lighterage
    lighterage_plan: LighterageResponse


class PortResponse(BaseModel):
    code: str
    name: str
    country: str
    is_indian_hub: bool
    max_draft: float
    max_loa: float
    max_beam: float
    discharge_rate: float
    load_rate: float
    is_anchorage: bool
    latitude: float
    longitude: float


# ── Port coordinate lookup table ──────────────────────────────────────────────
_PORT_COORDS: Dict[str, tuple] = {
    # Indian East Coast
    "PPA":             (20.2644,  86.6740),
    "VIZAG":           (17.6868,  83.2185),
    "GANGAVARAM":      (17.6220,  83.2310),
    "GOPALPUR":        (19.3090,  84.9660),
    "DHAMRA":          (20.7960,  86.9530),
    "SAGAR_SANDHEADS": (21.2500,  88.1500),
    "HALDIA":          (22.0257,  88.0583),
    # Global
    "HAY_POINT":       (-21.2700, 149.2990),
    "NEWCASTLE":       (-32.9267, 151.7841),
    "TABONEO":         (-3.7500,  114.4500),
    "BANJARMASIN":     (-3.3500,  114.5800),
    "MAPUTO":          (-25.9692,  32.5732),
    "BEIRA_NACALA":    (-19.8332,  34.8389),
    "NORFOLK":         (36.9460,  -76.3254),
    "BALTIMORE":       (39.2904,  -76.6122),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _port_to_response(port) -> PortResponse:
    coords = _PORT_COORDS.get(port.code, (0.0, 0.0))
    # Cap infinite LOA/Beam for JSON serialisation
    max_loa = port.max_loa if port.max_loa != float("inf") else 9999.0
    max_beam = port.max_beam if port.max_beam != float("inf") else 9999.0
    return PortResponse(
        code=port.code,
        name=port.name,
        country=port.country,
        is_indian_hub=port.is_indian_hub,
        max_draft=port.max_draft,
        max_loa=max_loa,
        max_beam=max_beam,
        discharge_rate=port.discharge_rate,
        load_rate=port.load_rate,
        is_anchorage=port.is_anchorage,
        latitude=coords[0],
        longitude=coords[1],
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/ports", response_model=List[PortResponse], summary="List all registered ports")
def get_ports():
    """Returns all 15 registered ports with coordinates and port constraints. Cached 24 hours."""
    now = time.time()
    if _port_cache["data"] is not None and (now - _port_cache["ts"]) < _PORT_CACHE_TTL:
        return _port_cache["data"]

    ports = [_port_to_response(p) for p in get_all_ports()]
    _port_cache["data"] = ports
    _port_cache["ts"] = now
    return ports


@app.post("/api/evaluate", response_model=EvaluationResponse, summary="Evaluate Spot vs. CVC financial decision")
def evaluate(request: EvaluationRequest):
    """
    Runs the full financial evaluation chain:
    1. Resolves port and vessel objects
    2. Runs feasibility check (lighterage detection)
    3. Gets ML quantile forecasts (p10/p50/p90)
    4. Computes per-voyage cost breakdown
    5. Computes break-even rate and probability
    6. Generates headline summary
    """
    # Resolve port objects
    supported_ports = ", ".join(sorted(ALL_PORTS.keys()))
    try:
        origin = get_port(request.origin_code)
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown port '{request.origin_code}'. Supported ports: {supported_ports}",
        )

    try:
        destination = get_port(request.destination_code)
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown port '{request.destination_code}'. Supported ports: {supported_ports}",
        )

    # Resolve vessel object
    supported_vessels = ", ".join(sorted(VESSEL_CLASSES.keys()))
    try:
        vessel = get_vessel_class(request.vessel_code)
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown vessel class '{request.vessel_code}'. Supported: {supported_vessels}",
        )

    # Run feasibility check to get lighterage plan
    try:
        feasibility_result = _feasibility.evaluate_vessel(
            vessel=vessel,
            cargo_tonnage=request.cargo_tonnage,
            origin=origin,
            destination=destination,
        )
        lighterage_plan = feasibility_result.lighterage_plan
    except Exception as exc:
        logger.exception("Feasibility check failed")
        raise HTTPException(status_code=500, detail=f"Feasibility check failed: {exc}")

    # Run financial evaluation
    try:
        result = _evaluator.evaluate(
            cargo_tonnage=request.cargo_tonnage,
            origin=origin,
            destination=destination,
            vessel=vessel,
            num_voyages=request.num_voyages,
            cvc_discount_pct=request.cvc_discount_pct,
            lighterage_plan=lighterage_plan,
        )
    except Exception as exc:
        logger.exception("Financial evaluation failed")
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {exc}")

    # Extract per-voyage quantile rate arrays
    p10_rates = [v.p10_spot_rate for v in result.voyages]
    p50_rates = [v.spot_freight_rate for v in result.voyages]
    p90_rates = [v.p90_spot_rate for v in result.voyages]

    # Build voyage response objects
    voyage_responses = [
        VoyageBreakdownResponse(
            voyage_number=v.voyage_number,
            spot_freight_rate=v.spot_freight_rate,
            spot_freight_cost=v.spot_freight_cost,
            cvc_freight_rate=v.cvc_freight_rate,
            cvc_freight_cost=v.cvc_freight_cost,
            bunker_adj_cost=v.bunker_adj_cost,
            port_charges=v.port_charges,
            wait_days=v.wait_days,
            demurrage_cost=v.demurrage_cost,
            lighterage_tonnage=v.lighterage_tonnage,
            lighterage_cost=v.lighterage_cost,
            spot_voyage_total=v.spot_voyage_total,
            cvc_voyage_total=v.cvc_voyage_total,
            voyage_savings=v.voyage_savings,
            p10_spot_rate=v.p10_spot_rate,
            p90_spot_rate=v.p90_spot_rate,
        )
        for v in result.voyages
    ]

    lp = result.lighterage_plan
    lighterage_response = LighterageResponse(
        is_required=lp.is_required,
        location=lp.location,
        excess_draft=lp.excess_draft,
        lightered_tonnage=lp.lightered_tonnage,
        retained_tonnage=lp.retained_tonnage,
        lighterage_cost=lp.lighterage_cost,
        time_penalty_days=lp.time_penalty_days,
        warning_message=lp.warning_message,
    )

    return EvaluationResponse(
        cargo_tonnage=result.cargo_tonnage,
        num_voyages=result.num_voyages,
        cvc_discount_pct=result.cvc_discount_pct,
        is_cvc_favorable=result.is_cvc_favorable,
        locked_cvc_rate=result.locked_cvc_rate,
        average_spot_rate=result.average_spot_rate,
        spot_total_usd=result.spot_total_usd,
        cvc_total_usd=result.cvc_total_usd,
        base_case_delta_usd=result.base_case_delta_usd,
        base_case_delta_inr=result.base_case_delta_inr,
        base_case_delta_cr=result.base_case_delta_cr,
        breakeven_spot_rate=result.breakeven_spot_rate,
        breakeven_probability_pct=result.breakeven_probability_pct,
        headline_summary=result.headline_summary,
        p10_spot_total_usd=result.p10_spot_total_usd,
        p90_spot_total_usd=result.p90_spot_total_usd,
        p10_rates=p10_rates,
        p50_rates=p50_rates,
        p90_rates=p90_rates,
        voyages=voyage_responses,
        lighterage_plan=lighterage_response,
    )


@app.get("/health", summary="Health check")
def health():
    return {"status": "ok"}
