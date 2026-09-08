// ─── Voyage Cost Assumptions ──────────────────────────────────────────────────
// Every number the Spot-vs-CVC engine uses that is not already in ports.ts,
// vessels.ts or the forecast series lives here, so a commercial user can audit
// the model without reading the code.

import type { VesselClass } from './vessels';

// ─── Currency ─────────────────────────────────────────────────────────────────

/** USD → INR. Freight is quoted in dollars; the board reads crores. */
export const USD_INR = 88.4;

/** One crore = 10 million rupees. */
export const CRORE = 1e7;

/** Convert a USD figure to INR crores. */
export function usdToCrore(usd: number): number {
  return (usd * USD_INR) / CRORE;
}

// ─── Bunkers ──────────────────────────────────────────────────────────────────

/** VLSFO burn at service speed on the laden leg, tonnes per day. */
export const BUNKER_LADEN_TPD: Record<VesselClass, number> = {
  Handysize: 21,
  Supramax: 27,
  Panamax: 32,
  Capesize: 45,
};

/** The ballast leg runs lighter and burns proportionally less. */
export const BALLAST_BURN_FACTOR = 0.82;

/** Auxiliaries and boilers while alongside or waiting at anchor, tonnes per day. */
export const BUNKER_PORT_TPD = 4.5;

/**
 * The bunker price the freight market is currently struck at. A voyage charter's
 * freight rate is all-in, so bunkers are not billed twice: the "bunker
 * adjustment" line carries only the deviation from this basis, which is what a
 * BAF clause actually settles. At this price the line is zero on both sides.
 */
export const BUNKER_BASIS_USD = 620;

/**
 * A consecutive voyage charter fixes the bunker basis at fixture and the owner
 * absorbs this share of any deviation from it. The charterer carries the rest.
 * Set to 1 for a fully hedged BAF clause, 0 for a full pass-through.
 */
export const CVC_BAF_HEDGE = 0.7;

// ─── Port charges ─────────────────────────────────────────────────────────────

export interface PortCharge {
  /** Cargo-handling and wharfage, USD per tonne. */
  perMtUsd: number;
  /** Port dues, pilotage, towage, berth hire and agency, USD per call. */
  callUsd: number;
}

/** Discharge-port charges, keyed by the port ids in ports.ts. */
export const DISCHARGE_PORT_CHARGES: Record<string, PortCharge> = {
  paradip: { perMtUsd: 1.35, callUsd: 58_000 },
  vizag: { perMtUsd: 1.48, callUsd: 62_000 },
  gangavaram: { perMtUsd: 1.55, callUsd: 66_000 },
  gopalpur: { perMtUsd: 1.2, callUsd: 44_000 },
  dhamra: { perMtUsd: 1.42, callUsd: 60_000 },
  'sagar-sandheads': { perMtUsd: 0.95, callUsd: 38_000 },
  haldia: { perMtUsd: 1.62, callUsd: 54_000 },
};

export const DEFAULT_DISCHARGE_CHARGE: PortCharge = { perMtUsd: 1.4, callUsd: 55_000 };

/** Load-port charges and berth throughput, keyed by the ids in ports.ts. */
export const LOAD_PORT_TERMS: Record<string, PortCharge & { loadRateTpd: number }> = {
  newcastle: { perMtUsd: 0.78, callUsd: 46_000, loadRateTpd: 60_000 },
  gladstone: { perMtUsd: 0.82, callUsd: 44_000, loadRateTpd: 55_000 },
  'abbot-point': { perMtUsd: 0.8, callUsd: 42_000, loadRateTpd: 50_000 },
  'hampton-roads': { perMtUsd: 0.95, callUsd: 52_000, loadRateTpd: 48_000 },
  beira: { perMtUsd: 1.1, callUsd: 38_000, loadRateTpd: 18_000 },
  nacala: { perMtUsd: 1.05, callUsd: 40_000, loadRateTpd: 22_000 },
  murmansk: { perMtUsd: 1.15, callUsd: 50_000, loadRateTpd: 30_000 },
  kalimantan: { perMtUsd: 0.72, callUsd: 34_000, loadRateTpd: 35_000 },
  balikpapan: { perMtUsd: 0.75, callUsd: 36_000, loadRateTpd: 32_000 },
};

export const DEFAULT_LOAD_TERMS = { perMtUsd: 0.9, callUsd: 44_000, loadRateTpd: 40_000 };

// ─── Waiting time and demurrage ───────────────────────────────────────────────

/**
 * Expected berth waiting days beyond laytime for an unscheduled spot arrival,
 * by the discharge port's congestion level.
 */
export const SPOT_WAIT_DAYS: Record<'low' | 'medium' | 'high', number> = {
  low: 1.2,
  medium: 2.9,
  high: 5.4,
};

/**
 * A consecutive voyage charter publishes its programme months ahead, so berth
 * windows are nominated in advance and expected waiting falls by this share.
 * This is the only structural advantage the model grants CVC outside the rate.
 */
export const CVC_WAIT_REDUCTION = 0.45;

/** Default demurrage exposure, USD per day, before the slider moves it. */
export const DEFAULT_DEMURRAGE_USD_PER_DAY = 22_000;

// ─── Lighterage ───────────────────────────────────────────────────────────────

/** Tonnes per centimetre immersion — how much cargo one centimetre of draft is worth. */
export const TONNES_PER_CM: Record<VesselClass, number> = {
  Handysize: 38,
  Supramax: 52,
  Panamax: 66,
  Capesize: 108,
};

/** Under-keel clearance held back from the port's stated draft. */
export const UKC_MARGIN_M = 0.4;

/** Barge hire and transhipment, USD per tonne lightered. */
export const LIGHTERAGE_USD_PER_MT = 4.6;

/** Barge fleet mobilisation at the anchorage, USD per call. */
export const LIGHTERAGE_MOB_USD = 65_000;

/** Extra days at the anchorage while lightering, per 25,000 T transhipped. */
export const LIGHTERAGE_DAYS_PER_25KT = 2.5;

// ─── Forecast statistics ──────────────────────────────────────────────────────

/**
 * The forecast's published band is a 90% interval, so its half-width is 1.645
 * standard deviations.
 */
export const BAND_Z = 1.645;

/**
 * Freight forecast errors are driven by the market level, not by month-specific
 * noise, so misses in one voyage month travel with the next. Averaging N voyages
 * therefore reduces uncertainty far less than independence would imply.
 */
export const RATE_ERROR_CORRELATION = 0.7;

// ─── Misc voyage overheads ────────────────────────────────────────────────────

/** Pilotage, shifting and survey days that fall outside cargo operations. */
export const FIXED_TURNAROUND_DAYS = 2;
