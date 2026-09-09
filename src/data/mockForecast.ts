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

// ─── Mock data generator ──────────────────────────────────────────────────────

function addDays(base: Date, days: number): string {
  const d = new Date(base);
  d.setDate(d.getDate() + days);
  return d.toISOString().split('T')[0];
}

function generateSeries(
  baseRate: number,
  startDaysAgo: number,
  horizonDays: number,
  volatility: number,
  trend: number,
): ForecastPoint[] {
  const today = new Date();
  const points: ForecastPoint[] = [];
  const totalHistorical = startDaysAgo;

  // Historical
  let rate = baseRate;
  for (let i = totalHistorical; i >= 0; i--) {
    rate += (Math.random() - 0.5) * volatility + trend * 0.1;
    rate = Math.max(rate, baseRate * 0.4);
    points.push({
      date: addDays(today, -i),
      historical: Math.round(rate),
      isToday: i === 0,
    });
  }

  // Forecast
  const lastHistorical = rate;
  for (let i = 1; i <= horizonDays; i++) {
    const forecastRate = lastHistorical + trend * i + (Math.random() - 0.5) * volatility * 0.5;
    const spread = volatility * 0.8 * Math.sqrt(i / 30);
    points.push({
      date: addDays(today, i),
      forecast: Math.round(Math.max(forecastRate, baseRate * 0.3)),
      lower: Math.round(Math.max(forecastRate - spread, baseRate * 0.2)),
      upper: Math.round(forecastRate + spread),
    });
  }

  return points;
}

// ─── Profiles per vessel class ────────────────────────────────────────────────

const profiles: Record<VesselClass, { base: number; vol: number; trend: number }> = {
  Handysize: { base: 12, vol: 3,  trend: 0.05  },
  Supramax:  { base: 16, vol: 5,  trend: 0.08  },
  Panamax:   { base: 20, vol: 7,  trend: -0.04 },
  Capesize:  { base: 28, vol: 12, trend: 0.15  },
};

const horizonDaysMap: Record<ForecastHorizon, number> = {
  '1M': 30,
  '3M': 90,
  '6M': 180,
};

type ForecastData = Record<VesselClass, Record<ForecastHorizon, ForecastPoint[]>>;

function buildForecastData(): ForecastData {
  const data = {} as ForecastData;
  const classes: VesselClass[] = ['Handysize', 'Supramax', 'Panamax', 'Capesize'];
  const horizons: ForecastHorizon[] = ['1M', '3M', '6M'];

  for (const cls of classes) {
    data[cls] = {} as Record<ForecastHorizon, ForecastPoint[]>;
    const p = profiles[cls];
    for (const h of horizons) {
      data[cls][h] = generateSeries(p.base, 90, horizonDaysMap[h], p.vol, p.trend);
    }
  }
  return data;
}

export const MOCK_FORECAST: ForecastData = buildForecastData();
