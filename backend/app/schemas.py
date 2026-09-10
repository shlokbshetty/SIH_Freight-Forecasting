"""Request and response models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

VesselClassName = Literal["Handysize", "Supramax", "Panamax", "Capesize"]


# ── /api/forecast ─────────────────────────────────────────────────────────────

class ForecastRequest(BaseModel):
    vessel_class: VesselClassName = "Supramax"
    horizon_days: Literal[30, 90, 180] = 90
    history_days: int = Field(180, ge=30, le=1095)
    #: Optional what-if overrides on the exogenous regressors, in natural units.
    #: ``{"bunker": 800}`` reprices the forecast at eight hundred dollar fuel.
    scenario: dict[str, float] | None = None


class SeriesPoint(BaseModel):
    date: str
    value: float


class IntervalPoint(BaseModel):
    date: str
    lower: float
    upper: float


class Driver(BaseModel):
    feature: str
    contribution: float
    key: str | None = None
    coefficient: float | None = None


class Accuracy(BaseModel):
    mape: float | None = None
    rmse: float | None = None
    folds: int | None = None
    horizon_days: int | None = None
    backtest: str | None = None


class ForecastResponse(BaseModel):
    vessel_class: VesselClassName
    unit: str = "USD/tonne"
    history: list[SeriesPoint]
    forecast: list[SeriesPoint]
    intervals: dict[str, list[IntervalPoint]]
    drivers: list[Driver]
    accuracy: Accuracy
    as_of: str
    sources_stale: list[str]
    model: str
    notes: list[str] = []


# ── /api/match ────────────────────────────────────────────────────────────────

BerthOutcome = Literal["ACCEPT_ALL_TIDE", "ACCEPT_HIGH_TIDE_ONLY", "REJECT"]


class MatchRequest(BaseModel):
    #: Slug ("vizag") or berth-table name ("Visakhapatnam"); both resolve.
    discharge_port_id: str
    cargo_tonnes: int = Field(..., gt=0, le=400_000)
    load_port_id: str | None = None
    commodity: str = "thermal_coal"
    #: Evaluate one stated draft instead of the class default.
    vessel_draft_m: float | None = Field(None, gt=0, le=30)


class Provenance(BaseModel):
    source_url: str | None = None
    source_date: str | None = None


class BerthCheckOut(BaseModel):
    berth_id: str
    berth_name: str
    outcome: BerthOutcome
    reason: str
    draft_headroom_m: float | None = None
    provenance: Provenance = Provenance()


class LighterageOut(BaseModel):
    node_id: str
    node_name: str
    tonnes_to_lighten: float
    barge_trips: int
    added_days: float
    cost_usd: float
    resulting_draft_m: float
    onward_berth_id: str | None
    onward_outcome: BerthOutcome
    narrative: str
    provenance: Provenance = Provenance()


class VesselVerdict(BaseModel):
    vessel_class: VesselClassName
    outcome: BerthOutcome
    reason: str
    laden_draft_m: float
    berth: dict | None = None
    turnaround_days: float | None = None
    estimated_rate_usd_per_t: float | None = None
    lighterage: LighterageOut | None = None
    considered: list[BerthCheckOut] = []


class MatchResponse(BaseModel):
    discharge_port_id: str
    discharge_port_name: str
    commodity: str
    cargo_tonnes: int
    as_of: str
    sources_stale: list[str]
    provenance: dict
    recommendations: list[VesselVerdict]


# ── /api/contract ─────────────────────────────────────────────────────────────

class ContractRequest(BaseModel):
    load_port_id: str = "newcastle"
    discharge_port_id: str = "paradip"
    commodity: str = "thermal_coal"
    vessel_class: VesselClassName = "Supramax"
    cargo_tonnes: int = Field(55_000, gt=0, le=400_000)
    num_voyages: int = Field(4, ge=1, le=12)
    bunker_price_usd: float | None = None
    demurrage_usd_per_day: float = 22_000
    cvc_discount_pct: float = Field(5.0, ge=0, le=40)


class ContractLineItem(BaseModel):
    label: str
    spot_cr: float
    cvc_cr: float
    note: str | None = None


class EvaluateRequest(BaseModel):
    """The evaluator page's request shape, kept as it was written."""

    cargo_tonnage: float = Field(..., ge=1_000, le=500_000)
    origin_code: str
    destination_code: str
    vessel_code: str
    num_voyages: int = Field(4, ge=1, le=12)
    cvc_discount_pct: float = Field(5.0, ge=0.0, le=15.0)


class MultiPortRequest(BaseModel):
    load_port_id: str = "newcastle"
    discharge_port_ids: list[str] = Field(default_factory=lambda: ["gangavaram", "haldia"], min_length=2, max_length=2)
    vessel_class: VesselClassName = "Panamax"
    commodity: str = "thermal_coal"
    total_tonnes: int = Field(72_000, gt=0, le=400_000)
    rate_usd_per_t: float | None = None
    bunker_price_usd: float | None = None
    demurrage_usd_per_day: float = 22_000


class ContractResponse(BaseModel):
    route: str
    vessel_class: VesselClassName
    num_voyages: int
    spot_total_cr: float
    cvc_total_cr: float
    delta_cr: float
    break_even_usd_per_t: float
    prob_spot_wins: float
    locked_rate_usd_per_t: float
    market_rate_usd_per_t: float
    forecast_avg_usd_per_t: float
    line_items: list[ContractLineItem]
    lighterage_tonnes: float
    blocked_reason: str | None
    #: Which berth she goes to, the tide verdict, and where that came from.
    berth: dict | None = None
    #: Period time charter priced over the same programme.
    ptc: dict | None = None
    #: "spot", "cvc" or "ptc".
    cheapest_structure: str | None = None
    voyages: list[dict] = []
    band: dict | None = None
    rate_distribution: dict | None = None
    profile: dict | None = None
    headline: str
    as_of: str
    sources_stale: list[str]


# ── /api/data/status ──────────────────────────────────────────────────────────

class SourceStatus(BaseModel):
    source: str
    last_fetched: str | None
    last_success: str | None
    is_stale: bool
    age_minutes: float | None
    row_count: int
    error: str | None
    #: True when the series stands in for something it is not. The Baltic feed
    #: is a CFD quote, not the licensed index; bunkers are indicative levels,
    #: not broker quotes. The UI is expected to label these.
    is_proxy: bool = False
    source_label: str | None = None
    notes: list[str] = []


class DataStatusResponse(BaseModel):
    as_of: str
    offline_mode: bool
    stale_after_minutes: int
    snapshot_provenance: str | None
    sources: list[SourceStatus]
