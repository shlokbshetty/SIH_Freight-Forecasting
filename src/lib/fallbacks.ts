// ─── Bundled data, shaped like the API ────────────────────────────────────────
//
// The dashboard shipped as a fully static app and must keep working that way.
// These build API-shaped objects out of the data in src/data, so every screen
// has something real to render when the backend is unreachable.
//
// They are honest stand-ins, not pretend live data: the pages that use them
// show a "bundled data" badge, and the fields the backend alone can supply
// (berth rows, provenance, backtest accuracy) come back empty rather than
// invented.

import { DISCHARGE_PORTS, LOADING_PORTS } from '../data/ports';
import { VESSEL_CLASSES, VESSEL_SPECS, type VesselClass } from '../data/vessels';
import { MOCK_FORECAST, type ForecastHorizon } from '../data/mockForecast';
import { assessLighterage, evaluate, type CvcInputs } from './cvcEngine';
import type {
  BerthOutcome, ContractResponse, ForecastResponse, MatchResponse,
  PortsResponse, VesselVerdict,
} from './apiTypes';

const nowIso = () => new Date().toISOString();

const EMPTY_PROVENANCE: PortsResponse['provenance'] = {
  berth_rows: 0,
  ports: [],
  lighterage_nodes: [],
  source_dates: [],
  sources: [],
  caveat: 'Bundled reference data. Berth-level detail and provenance come from the backend.',
};

// ─── /api/ports ───────────────────────────────────────────────────────────────

export function fallbackPorts(): PortsResponse {
  return {
    as_of: nowIso(),
    sources_stale: [],
    provenance: EMPTY_PROVENANCE,
    commodities: ['thermal_coal', 'coking_coal', 'iron_ore', 'bauxite', 'limestone', 'fertiliser', 'general'],
    discharge_ports: DISCHARGE_PORTS.map(p => ({
      id: p.id,
      name: p.name,
      lat: p.lat,
      lng: p.lng,
      max_draft_m: p.maxDraftM,
      current_draft_m: p.currentDraftM,
      max_loa_m: p.maxLoaM,
      berth_count: p.berthCount,
      berths_available: p.berthsAvailable,
      cargo_rate_tpd: p.cargoRateTpd,
      lighterage_required: p.lighterageRequired,
      congestion_level: p.congestionLevel,
      notes: p.notes,
      berth_port_name: p.name,
      is_anchorage: p.lighterageRequired,
      // Berth-level rows only exist server-side.
      berths: [],
      lighterage_nodes: [],
      deepest_berth_m: p.currentDraftM,
      deepest_on_tide_m: p.maxDraftM,
      live: { wait_days: null, vessels_at_anchor: null, observed_at: null, source: null },
    })),
    loading_ports: LOADING_PORTS.map(p => ({
      id: p.id, name: p.name, country: p.country, lat: p.lat, lng: p.lng,
      commodities: [...p.commodities],
    })),
    vessel_specs: Object.fromEntries(
      VESSEL_CLASSES.map(c => {
        const s = VESSEL_SPECS[c];
        return [c, {
          vessel_class: c,
          dwt_min: s.dwt.min, dwt_max: s.dwt.max,
          loa_m: s.loaM, beam_m: s.beamM,
          laden_draft_m: s.ladenDraftM, ballast_draft_m: s.ballastDraftM,
          speed_kts: s.speedKts, color: s.color, description: s.description,
        }];
      }),
    ),
  };
}

// ─── /api/forecast ────────────────────────────────────────────────────────────

function horizonFor(days: number): ForecastHorizon {
  return days <= 30 ? '1M' : days <= 90 ? '3M' : '6M';
}

export function fallbackForecast(vesselClass: VesselClass, horizonDays: number): ForecastResponse {
  const raw = MOCK_FORECAST[vesselClass][horizonFor(horizonDays)];
  const history = raw.filter(d => d.historical !== undefined)
    .map(d => ({ date: d.date, value: d.historical! }));
  const forward = raw.filter(d => d.forecast !== undefined).slice(0, horizonDays);

  // The bundled series publishes one band. Treat it as the 80% interval and
  // widen it by the normal-ratio for 95%, rather than claiming two measured ones.
  const widen = 1.96 / 1.2816;

  return {
    vessel_class: vesselClass,
    unit: 'USD/tonne',
    history,
    forecast: forward.map(d => ({ date: d.date, value: d.forecast! })),
    intervals: {
      p80: forward.map(d => ({ date: d.date, lower: d.lower!, upper: d.upper! })),
      p95: forward.map(d => {
        const mid = d.forecast!;
        return {
          date: d.date,
          lower: +(mid - (mid - d.lower!) * widen).toFixed(2),
          upper: +(mid + (d.upper! - mid) * widen).toFixed(2),
        };
      }),
    },
    drivers: [],
    accuracy: { mape: null, rmse: null, folds: null, horizon_days: horizonDays, backtest: null },
    as_of: nowIso(),
    sources_stale: [],
    model: 'bundled',
    notes: ['Backend unreachable. Showing the series bundled with the app; no fitted model, no backtest.'],
  };
}

// ─── /api/series ──────────────────────────────────────────────────────────────

export interface BundledSeries {
  as_of: string;
  series: Record<string, {
    adapter: string;
    source: string;
    is_proxy: boolean;
    points: { date: string; value: number }[];
  }>;
}

/**
 * Route rates from the bundled forecast series.
 *
 * Only the freight rates are available offline. The Baltic proxy, bunkers,
 * commodities and the exchange rate are ingested server-side and have no bundled
 * equivalent, so they come back absent and the screen shows a dash rather than
 * a number nobody can source.
 */
export function fallbackMarketSeries(): BundledSeries {
  const series: BundledSeries['series'] = {};
  for (const cls of VESSEL_CLASSES) {
    const points = MOCK_FORECAST[cls]['1M']
      .filter(d => d.historical !== undefined)
      .slice(-30)
      .map(d => ({ date: d.date, value: d.historical! }));
    if (points.length) {
      series[`freight.rate.${cls.toLowerCase()}`] = {
        adapter: 'freight', source: 'bundled', is_proxy: true, points,
      };
    }
  }
  return { as_of: nowIso(), series };
}

// ─── /api/match ───────────────────────────────────────────────────────────────

const OUTCOME_BY_MARGIN = (margin: number, blocked: boolean): BerthOutcome =>
  blocked ? 'REJECT' : margin >= 1.0 ? 'ACCEPT_ALL_TIDE' : 'ACCEPT_HIGH_TIDE_ONLY';

export function fallbackMatch(portId: string, cargoTonnes: number, commodity: string): MatchResponse {
  const port = DISCHARGE_PORTS.find(p => p.id === portId) ?? DISCHARGE_PORTS[0];

  const recommendations: VesselVerdict[] = VESSEL_CLASSES.map(cls => {
    const spec = VESSEL_SPECS[cls];
    const lighterage = assessLighterage(port, cls, cargoTonnes);
    const utilisation = Math.max(0, Math.min(1, cargoTonnes / spec.dwt.max));
    const laden = spec.ballastDraftM + (spec.ladenDraftM - spec.ballastDraftM) * utilisation;
    const margin = port.currentDraftM - laden;
    const loaBlocked = spec.loaM > port.maxLoaM;

    return {
      vessel_class: cls,
      outcome: OUTCOME_BY_MARGIN(margin, loaBlocked || margin < 0),
      reason: loaBlocked
        ? `LOA ${spec.loaM} m exceeds ${port.name}'s ${port.maxLoaM} m limit`
        : margin < 0
          ? `Laden draft ${laden.toFixed(1)} m against ${port.name}'s ${port.currentDraftM.toFixed(1)} m`
          : `${cls} clears ${port.name} with ${margin.toFixed(1)} m draft margin`,
      laden_draft_m: +laden.toFixed(2),
      berth: null,
      turnaround_days: +(cargoTonnes / Math.max(1, port.cargoRateTpd)).toFixed(2),
      estimated_rate_usd_per_t: null,
      lighterage: lighterage.required
        ? {
            node_id: 'sagar-sandheads', node_name: 'Sagar / Sandheads',
            tonnes_to_lighten: +lighterage.tonnesToLighten.toFixed(1),
            barge_trips: Math.ceil(lighterage.tonnesToLighten / 8000),
            added_days: +lighterage.extraDays.toFixed(2),
            cost_usd: +lighterage.costPerVoyageUsd.toFixed(2),
            resulting_draft_m: +(port.currentDraftM - 0.4).toFixed(2),
            onward_berth_id: null, onward_outcome: 'ACCEPT_ALL_TIDE',
            narrative: lighterage.reason,
            provenance: {},
          }
        : null,
      considered: [],
    };
  });

  const rank: Record<BerthOutcome, number> = {
    ACCEPT_ALL_TIDE: 0, ACCEPT_HIGH_TIDE_ONLY: 1, REJECT: 2,
  };
  recommendations.sort((a, b) => rank[a.outcome] - rank[b.outcome]);

  return {
    discharge_port_id: port.id,
    discharge_port_name: port.name,
    commodity,
    cargo_tonnes: cargoTonnes,
    as_of: nowIso(),
    sources_stale: [],
    provenance: EMPTY_PROVENANCE,
    recommendations,
  };
}

// ─── /api/contract ────────────────────────────────────────────────────────────

export function fallbackContract(inputs: CvcInputs): ContractResponse {
  const r = evaluate(inputs);
  return {
    route: `${r.loadPortName} to ${r.dischargePortName}`,
    vessel_class: inputs.vesselClass,
    num_voyages: inputs.numVoyages,
    spot_total_cr: +r.spot.totalCr.toFixed(3),
    cvc_total_cr: +r.cvc.totalCr.toFixed(3),
    delta_cr: +r.deltaCr.toFixed(3),
    break_even_usd_per_t: +r.breakEvenUsdPerMt.toFixed(3),
    prob_spot_wins: +r.probSpotWins.toFixed(4),
    locked_rate_usd_per_t: +r.lockedRateUsdPerMt.toFixed(3),
    market_rate_usd_per_t: +r.marketRateUsdPerMt.toFixed(3),
    forecast_avg_usd_per_t: +r.spot.avgRateUsdPerMt.toFixed(3),
    line_items: r.lineItems.map(l => ({
      label: l.label, spot_cr: +l.spotCr.toFixed(3), cvc_cr: +l.cvcCr.toFixed(3), note: l.note,
    })),
    lighterage_tonnes: +r.lighterage.tonnesToLighten.toFixed(1),
    blocked_reason: r.feasibility.blocked ? r.feasibility.reason : null,
    berth: null,
    // Period time charter is priced server-side only: it needs the daily hire
    // table, which is not bundled with the app.
    ptc: null,
    cheapest_structure: r.cvcWins ? 'cvc' : 'spot',
    voyages: r.spot.voyages.map((v, i) => ({
      index: v.index,
      departure_day: v.departureDay,
      rate_usd_per_t: +v.rateUsdPerMt.toFixed(3),
      spot_cr: +((v.total * 88.4) / 1e7).toFixed(3),
      cvc_cr: +((r.cvc.voyages[i].total * 88.4) / 1e7).toFixed(3),
    })),
    band: {
      low_avg_rate: +r.band.lowAvgRate.toFixed(3),
      high_avg_rate: +r.band.highAvgRate.toFixed(3),
      low_delta_cr: +r.band.lowDeltaCr.toFixed(3),
      high_delta_cr: +r.band.highDeltaCr.toFixed(3),
    },
    rate_distribution: {
      mean: +r.rateDistribution.mean.toFixed(3),
      sd: +r.rateDistribution.sd.toFixed(4),
    },
    profile: {
      distance_nm: +r.profile.distanceNm.toFixed(1),
      sea_days: +r.profile.seaDays.toFixed(2),
      cargo_days: +r.profile.cargoDays.toFixed(2),
      wait_days_spot: +r.profile.waitDaysSpot.toFixed(2),
      round_trip_days: +r.profile.roundTripDays.toFixed(2),
      bunker_tonnes: +r.profile.bunkerTonnes.toFixed(1),
    },
    headline: r.headline,
    as_of: nowIso(),
    sources_stale: [],
  };
}
