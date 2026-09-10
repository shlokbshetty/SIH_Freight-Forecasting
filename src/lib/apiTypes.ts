// ─── Shapes returned by the FastAPI backend ───────────────────────────────────
// Mirrors backend/app/schemas.py. Keep the two in step.

export type BerthOutcome = 'ACCEPT_ALL_TIDE' | 'ACCEPT_HIGH_TIDE_ONLY' | 'REJECT';
export type VesselClassName = 'Handysize' | 'Supramax' | 'Panamax' | 'Capesize';

export interface Provenance {
  source_url?: string | null;
  source_date?: string | null;
}

// ─── /api/data/status ─────────────────────────────────────────────────────────

export interface SourceStatus {
  source: string;
  last_fetched: string | null;
  last_success: string | null;
  is_stale: boolean;
  age_minutes: number | null;
  row_count: number;
  error: string | null;
  /** True when the series stands in for something it is not. */
  is_proxy: boolean;
  source_label: string | null;
  notes: string[];
}

export interface DataStatusResponse {
  as_of: string;
  offline_mode: boolean;
  stale_after_minutes: number;
  snapshot_provenance: string | null;
  sources: SourceStatus[];
}

// ─── /api/ports ───────────────────────────────────────────────────────────────

export interface Berth {
  port: string;
  berth_id: string;
  berth_name: string;
  operator: string;
  commodities: string[];
  loa_max_m: number;
  beam_max_m: number;
  draft_max_m: number;
  draft_max_on_tide_m: number;
  tide_required_m: number;
  night_restricted: boolean;
  discharge_rate_tpd: number;
  mechanised: boolean;
  source_url: string;
  source_date: string;
  provenance: Provenance;
}

export interface LighterageNode {
  node_id: string;
  node_name: string;
  port_served: string;
  lat: number;
  lng: number;
  max_draft_m: number;
  lighterage_rate_tpd: number;
  barge_capacity_t: number;
  transfer_cost_usd_per_t: number;
  mobilisation_usd: number;
  provenance: Provenance;
}

export interface PortEntry {
  id: string;
  name: string;
  lat: number;
  lng: number;
  max_draft_m: number;
  current_draft_m: number;
  max_loa_m: number;
  berth_count: number;
  berths_available: number;
  cargo_rate_tpd: number;
  lighterage_required: boolean;
  congestion_level: 'low' | 'medium' | 'high';
  notes?: string;
  berth_port_name: string;
  is_anchorage: boolean;
  berths: Berth[];
  lighterage_nodes: LighterageNode[];
  deepest_berth_m: number | null;
  deepest_on_tide_m: number | null;
  live: {
    wait_days: number | null;
    vessels_at_anchor: number | null;
    observed_at: string | null;
    source: string | null;
  };
}

export interface PortsResponse {
  as_of: string;
  sources_stale: string[];
  provenance: {
    berth_rows: number;
    ports: string[];
    lighterage_nodes: string[];
    source_dates: string[];
    sources: string[];
    caveat: string;
  };
  commodities: string[];
  discharge_ports: PortEntry[];
  loading_ports: { id: string; name: string; country: string; lat: number; lng: number; commodities: string[] }[];
  vessel_specs: Record<string, {
    vessel_class: VesselClassName;
    dwt_min: number; dwt_max: number;
    loa_m: number; beam_m: number;
    laden_draft_m: number; ballast_draft_m: number;
    speed_kts: number; color: string; description: string;
  }>;
}

// ─── /api/match ───────────────────────────────────────────────────────────────

export interface BerthCheck {
  berth_id: string;
  berth_name: string;
  outcome: BerthOutcome;
  reason: string;
  draft_headroom_m: number | null;
  provenance: Provenance;
}

export interface LighteragePlan {
  node_id: string;
  node_name: string;
  tonnes_to_lighten: number;
  barge_trips: number;
  added_days: number;
  cost_usd: number;
  resulting_draft_m: number;
  onward_berth_id: string | null;
  onward_outcome: BerthOutcome;
  narrative: string;
  provenance: Provenance;
}

export interface VesselVerdict {
  vessel_class: VesselClassName;
  outcome: BerthOutcome;
  reason: string;
  laden_draft_m: number;
  berth: Berth | null;
  turnaround_days: number | null;
  estimated_rate_usd_per_t: number | null;
  lighterage: LighteragePlan | null;
  considered: BerthCheck[];
}

export interface MatchResponse {
  discharge_port_id: string;
  discharge_port_name: string;
  commodity: string;
  cargo_tonnes: number;
  as_of: string;
  sources_stale: string[];
  provenance: PortsResponse['provenance'];
  recommendations: VesselVerdict[];
}

// ─── /api/forecast ────────────────────────────────────────────────────────────

export interface SeriesPoint { date: string; value: number }
export interface IntervalPoint { date: string; lower: number; upper: number }
export interface Driver { feature: string; contribution: number; key?: string | null; coefficient?: number | null }

export interface ForecastResponse {
  vessel_class: VesselClassName;
  unit: string;
  history: SeriesPoint[];
  forecast: SeriesPoint[];
  intervals: { p80: IntervalPoint[]; p95: IntervalPoint[] };
  drivers: Driver[];
  accuracy: {
    mape: number | null;
    rmse: number | null;
    folds: number | null;
    horizon_days: number | null;
    backtest: string | null;
  };
  as_of: string;
  sources_stale: string[];
  /** "sarimax" when the fitted model answered, "naive-fallback" otherwise. */
  model: string;
  notes: string[];
}

// ─── /api/contract ────────────────────────────────────────────────────────────

export interface ContractLineItem { label: string; spot_cr: number; cvc_cr: number; note?: string | null }

export interface PeriodTimeCharter {
  hire_usd_per_day: number;
  hire_days: number;
  programme_days: number;
  hire_cr: number;
  bunkers_cr: number;
  port_and_lighterage_cr: number;
  total_cr: number;
  vs_spot_cr: number;
  vs_cvc_cr: number;
  note: string;
}

export interface ContractVoyage {
  index: number;
  departure_day: number;
  rate_usd_per_t: number;
  spot_cr: number;
  cvc_cr: number;
}

export interface VoyageProfile {
  distance_nm: number;
  sea_days: number;
  cargo_days: number;
  wait_days_spot: number;
  round_trip_days: number;
  bunker_tonnes: number;
}

export interface ContractResponse {
  route: string;
  vessel_class: VesselClassName;
  num_voyages: number;
  spot_total_cr: number;
  cvc_total_cr: number;
  delta_cr: number;
  break_even_usd_per_t: number;
  prob_spot_wins: number;
  locked_rate_usd_per_t: number;
  market_rate_usd_per_t: number;
  forecast_avg_usd_per_t: number;
  line_items: ContractLineItem[];
  lighterage_tonnes: number;
  blocked_reason: string | null;
  berth: {
    outcome: BerthOutcome;
    berth_id: string | null;
    berth_name: string | null;
    discharge_rate_tpd: number;
    reason: string;
    provenance: Provenance;
  } | null;
  ptc: PeriodTimeCharter | null;
  cheapest_structure: 'spot' | 'cvc' | 'ptc' | null;
  voyages: ContractVoyage[];
  band: { low_avg_rate: number; high_avg_rate: number; low_delta_cr: number; high_delta_cr: number } | null;
  rate_distribution: { mean: number; sd: number } | null;
  profile: VoyageProfile | null;
  headline: string;
  as_of: string;
  sources_stale: string[];
}

// ─── /api/contract/multiport ──────────────────────────────────────────────────

export interface MultiPortCall {
  port_id: string;
  port_name: string;
  tonnes: number;
  arrival_draft_m: number;
  outcome: BerthOutcome;
  berth_id: string | null;
  berth_name: string | null;
  reason: string;
  lighterage_tonnes: number;
  lighterage_cost_usd: number;
  port_charges_usd: number;
  days: number;
  demurrage_usd: number;
  blocked: boolean;
  provenance: Provenance;
}

export interface MultiPortOption {
  label: string;
  first_tonnes?: number;
  second_tonnes?: number;
  calls: MultiPortCall[];
  extra_days?: number;
  total_usd: number;
  total_cr: number;
  port_days: number;
  feasible: boolean;
  vs_baseline_cr?: number;
}

export interface MultiPortResponse {
  vessel_class: VesselClassName;
  commodity: string;
  total_tonnes: number;
  rate_usd_per_t: number;
  inter_port_nm: number;
  inter_port_days: number;
  baseline: MultiPortOption;
  options: MultiPortOption[];
  best: MultiPortOption | null;
  verdict: string;
  as_of: string;
  sources_stale: string[];
}
