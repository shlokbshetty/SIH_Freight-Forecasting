import type { VesselClass } from './vessels';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ForecastPoint {
  date: string;         // ISO date string
  historical?: number;  // Actual rate (USD/MT or BDI points)
  forecast?: number;    // Predicted rate
  lower?: number;       // Lower confidence bound
  upper?: number;       // Upper confidence bound
  isToday?: boolean;
}

export type ForecastHorizon = '1M' | '3M' | '6M';

/** A forecast rate for one future departure, with its published band. */
export interface RateOutlook {
  dayOffset: number;   // days from today
  label: string;       // "Mar 2026"
  mean: number;        // USD / MT
  lower: number;       // USD / MT, 90% band floor
  upper: number;       // USD / MT, 90% band ceiling
}

// ─── Deterministic noise ──────────────────────────────────────────────────────
// A seeded generator keeps the series stable across reloads, so a quoted
// break-even or probability is reproducible instead of changing on refresh.

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ─── Mock data generator ──────────────────────────────────────────────────────

function addDays(base: Date, days: number): string {
  const d = new Date(base);
  d.setDate(d.getDate() + days);
  return d.toISOString().split('T')[0];
}

function round1(n: number): number {
  return Math.round(n * 10) / 10;
}

/** Daily pull back toward the route's structural rate. */
const MEAN_REVERSION = 0.06;

/** Daily shock size, as a share of the class's volatility parameter. */
const SHOCK_SCALE = 0.45;

function generateSeries(
  baseRate: number,
  startDaysAgo: number,
  horizonDays: number,
  volatility: number,
  trend: number,
  seed: number,
): ForecastPoint[] {
  const rand = mulberry32(seed);
  const today = new Date();
  const points: ForecastPoint[] = [];

  // `trend` is a per-day drift once scaled; historical and forecast limbs share
  // it so the curve is continuous where the forecast takes over.
  const driftPerDay = trend * 0.1;

  // Historical. Freight rates are mean-reverting: a squeeze pulls tonnage onto
  // the route and the premium decays. Without that pull a 90-day random walk
  // wanders far enough to put a Capesize under a Handysize, so the series is an
  // Ornstein-Uhlenbeck walk rather than a free one.
  let rate = baseRate;
  for (let i = startDaysAgo; i >= 0; i--) {
    rate += MEAN_REVERSION * (baseRate - rate) + (rand() - 0.5) * volatility * SHOCK_SCALE + driftPerDay;
    rate = Math.max(rate, baseRate * 0.4);
    points.push({
      date: addDays(today, -i),
      historical: round1(rate),
      isToday: i === 0,
    });
  }

  // Forecast — the band widens with the square root of horizon, as a random
  // walk's dispersion does.
  const lastHistorical = rate;
  for (let i = 1; i <= horizonDays; i++) {
    const forecastRate = lastHistorical + driftPerDay * i + (rand() - 0.5) * volatility * 0.25;
    const spread = volatility * 0.35 * Math.sqrt(i / 30);
    points.push({
      date: addDays(today, i),
      forecast: round1(Math.max(forecastRate, baseRate * 0.3)),
      lower: round1(Math.max(forecastRate - spread, baseRate * 0.25)),
      upper: round1(forecastRate + spread),
    });
  }

  return points;
}

// ─── Profiles per vessel class ────────────────────────────────────────────────

const profiles: Record<VesselClass, { base: number; vol: number; trend: number; seed: number }> = {
  Handysize: { base: 12, vol: 3, trend: 0.05, seed: 1041 },
  Supramax: { base: 16, vol: 5, trend: 0.08, seed: 2087 },
  Panamax: { base: 20, vol: 7, trend: -0.04, seed: 3163 },
  Capesize: { base: 28, vol: 12, trend: 0.15, seed: 4211 },
};

const horizonDaysMap: Record<ForecastHorizon, number> = {
  '1M': 30,
  '3M': 90,
  '6M': 180,
};

const HORIZON_MAX_DAYS = horizonDaysMap['6M'];

type ForecastData = Record<VesselClass, Record<ForecastHorizon, ForecastPoint[]>>;

function buildForecastData(): ForecastData {
  const data = {} as ForecastData;
  const classes: VesselClass[] = ['Handysize', 'Supramax', 'Panamax', 'Capesize'];
  const horizons: ForecastHorizon[] = ['1M', '3M', '6M'];

  for (const cls of classes) {
    data[cls] = {} as Record<ForecastHorizon, ForecastPoint[]>;
    const p = profiles[cls];
    for (const h of horizons) {
      // Same seed per class, so every horizon is a window on one coherent story.
      data[cls][h] = generateSeries(p.base, 90, horizonDaysMap[h], p.vol, p.trend, p.seed);
    }
  }
  return data;
}

export const MOCK_FORECAST: ForecastData = buildForecastData();

// ─── Reading rates out of the forecast ────────────────────────────────────────

/** Forecast points of the 6-month series, indexed so that element j is day j+1. */
const forecastLegByClass: Record<VesselClass, ForecastPoint[]> = {
  Handysize: MOCK_FORECAST.Handysize['6M'].filter(p => p.forecast !== undefined),
  Supramax: MOCK_FORECAST.Supramax['6M'].filter(p => p.forecast !== undefined),
  Panamax: MOCK_FORECAST.Panamax['6M'].filter(p => p.forecast !== undefined),
  Capesize: MOCK_FORECAST.Capesize['6M'].filter(p => p.forecast !== undefined),
};

/** Today's spot rate for a vessel class — the last observed point, USD/MT. */
export function getCurrentSpotRate(cls: VesselClass): number {
  const history = MOCK_FORECAST[cls]['6M'].filter(p => p.historical !== undefined);
  return history.at(-1)?.historical ?? profiles[cls].base;
}

/** Mean of a numeric field across a window of forecast points. */
function windowMean(leg: ForecastPoint[], centreIdx: number, halfWidth: number, key: 'forecast' | 'lower' | 'upper'): number {
  const from = Math.max(0, centreIdx - halfWidth);
  const to = Math.min(leg.length - 1, centreIdx + halfWidth);
  let sum = 0;
  let n = 0;
  for (let i = from; i <= to; i++) {
    const v = leg[i][key];
    if (v !== undefined) {
      sum += v;
      n++;
    }
  }
  return n > 0 ? sum / n : 0;
}

function monthLabel(dayOffset: number): string {
  const d = new Date();
  d.setDate(d.getDate() + dayOffset);
  return d.toLocaleDateString('en-IN', { month: 'short', year: 'numeric' });
}

/**
 * The forecast rate for a departure `dayOffset` days out, smoothed over a
 * fortnight so a single noisy day cannot move a chartering decision. Beyond the
 * published six-month horizon the drift is extended and the band keeps widening
 * with the square root of time.
 */
export function getRateOutlook(cls: VesselClass, dayOffset: number): RateOutlook {
  const leg = forecastLegByClass[cls];
  const label = monthLabel(dayOffset);

  if (dayOffset <= HORIZON_MAX_DAYS) {
    const idx = Math.max(0, Math.min(leg.length - 1, Math.round(dayOffset) - 1));
    return {
      dayOffset,
      label,
      mean: windowMean(leg, idx, 7, 'forecast'),
      lower: windowMean(leg, idx, 7, 'lower'),
      upper: windowMean(leg, idx, 7, 'upper'),
    };
  }

  // Past the horizon: continue the last month's slope, widen the band by √t.
  const endIdx = leg.length - 1;
  const meanEnd = windowMean(leg, endIdx, 7, 'forecast');
  const meanPrior = windowMean(leg, endIdx - 30, 7, 'forecast');
  const slopePerDay = (meanEnd - meanPrior) / 30;
  const extraDays = dayOffset - HORIZON_MAX_DAYS;
  const mean = Math.max(meanEnd * 0.3, meanEnd + slopePerDay * extraDays);

  const halfBandEnd = (windowMean(leg, endIdx, 7, 'upper') - windowMean(leg, endIdx, 7, 'lower')) / 2;
  const halfBand = halfBandEnd * Math.sqrt(dayOffset / HORIZON_MAX_DAYS);

  return {
    dayOffset,
    label,
    mean,
    lower: Math.max(mean * 0.25, mean - halfBand),
    upper: mean + halfBand,
  };
}
