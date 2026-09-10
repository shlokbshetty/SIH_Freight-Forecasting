/**
 * API client for the Maritime Freight Forecasting backend.
 * Connects to FastAPI endpoints at http://localhost:8000
 */

const API_BASE = "http://localhost:8000";

// ─── Request / Response types ─────────────────────────────────────────────────

export interface EvaluationRequest {
  cargo_tonnage: number;
  origin_code: string;
  destination_code: string;
  vessel_code: string;
  num_voyages: number;
  cvc_discount_pct: number;
}

export interface LighterageResponse {
  is_required: boolean;
  location: string | null;
  excess_draft: number;
  lightered_tonnage: number;
  retained_tonnage: number;
  lighterage_cost: number;
  time_penalty_days: number;
  warning_message: string | null;
}

export interface VoyageBreakdown {
  voyage_number: number;
  spot_freight_rate: number;
  spot_freight_cost: number;
  cvc_freight_rate: number;
  cvc_freight_cost: number;
  bunker_adj_cost: number;
  port_charges: number;
  wait_days: number;
  demurrage_cost: number;
  lighterage_tonnage: number;
  lighterage_cost: number;
  spot_voyage_total: number;
  cvc_voyage_total: number;
  voyage_savings: number;
  p10_spot_rate: number;
  p90_spot_rate: number;
}

export interface EvaluationResult {
  cargo_tonnage: number;
  num_voyages: number;
  cvc_discount_pct: number;
  is_cvc_favorable: boolean;
  locked_cvc_rate: number;
  average_spot_rate: number;
  spot_total_usd: number;
  cvc_total_usd: number;
  base_case_delta_usd: number;
  base_case_delta_inr: number;
  base_case_delta_cr: number;
  breakeven_spot_rate: number;
  breakeven_probability_pct: number;
  headline_summary: string;
  p10_spot_total_usd: number;
  p90_spot_total_usd: number;
  p10_rates: number[];
  p50_rates: number[];
  p90_rates: number[];
  voyages: VoyageBreakdown[];
  lighterage_plan: LighterageResponse;
}

export interface PortResponse {
  code: string;
  name: string;
  country: string;
  is_indian_hub: boolean;
  max_draft: number;
  max_loa: number;
  max_beam: number;
  discharge_rate: number;
  load_rate: number;
  is_anchorage: boolean;
  latitude: number;
  longitude: number;
}

// ─── API functions ────────────────────────────────────────────────────────────

export async function fetchPorts(): Promise<PortResponse[]> {
  const res = await fetch(`${API_BASE}/api/ports`);
  if (!res.ok) {
    throw new Error(`Failed to fetch ports: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function evaluate(request: EvaluationRequest): Promise<EvaluationResult> {
  const res = await fetch(`${API_BASE}/api/evaluate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Evaluation failed: ${res.status}`);
  }
  return res.json();
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Maps time horizon in months to num_voyages. */
export function horizonToVoyages(months: 1 | 3 | 6): number {
  const map: Record<number, number> = { 1: 1, 3: 4, 6: 8 };
  return map[months] ?? 4;
}
