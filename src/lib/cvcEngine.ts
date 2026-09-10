// ─── Spot vs Consecutive Voyage Charter — costing engine ──────────────────────
//
// A spot fixture prices every voyage at whatever the market is that week. A
// consecutive voyage charter (CVC) locks one rate across N voyages: the buyer
// gives up the upside to buy certainty. This module puts a rupee value on that
// trade, and — because the answer is only as good as the forecast behind it —
// reports the break-even spot rate and the probability the forecast is wrong
// enough for spot to win.
//
// Per voyage:
//   cost = freight rate ($/T x tonnage)
//        + bunker adjustment
//        + port charges (load + discharge)
//        + demurrage expectation (expected wait days x demurrage rate/day)
//        + lighterage (only when the constraint engine flags it)

import { DISCHARGE_PORTS, LOADING_PORTS, type Port } from '../data/ports';
import { VESSEL_SPECS, type VesselClass } from '../data/vessels';
import { getRateOutlook, getCurrentSpotRate, type RateOutlook } from '../data/mockForecast';
import {
  BALLAST_BURN_FACTOR,
  BAND_Z,
  BUNKER_BASIS_USD,
  BUNKER_LADEN_TPD,
  BUNKER_PORT_TPD,
  CVC_BAF_HEDGE,
  CVC_WAIT_REDUCTION,
  DEFAULT_DISCHARGE_CHARGE,
  DEFAULT_LOAD_TERMS,
  DISCHARGE_PORT_CHARGES,
  FIXED_TURNAROUND_DAYS,
  LIGHTERAGE_DAYS_PER_25KT,
  LIGHTERAGE_MOB_USD,
  LIGHTERAGE_USD_PER_MT,
  LOAD_PORT_TERMS,
  RATE_ERROR_CORRELATION,
  SPOT_WAIT_DAYS,
  TONNES_PER_CM,
  UKC_MARGIN_M,
  usdToCrore,
} from '../data/costAssumptions';

// ─── Inputs & outputs ─────────────────────────────────────────────────────────

export interface CvcInputs {
  loadPortId: string;
  dischargePortId: string;
  vesselClass: VesselClass;
  /** Cargo lifted per voyage, tonnes. */
  cargoTonnes: number;
  /** Number of voyages in the programme. */
  numVoyages: number;
  /** VLSFO, USD per tonne. */
  bunkerPriceUsd: number;
  /** Demurrage exposure, USD per day. */
  demurrageUsdPerDay: number;
  /** Discount the CVC is negotiated at, off today's market rate, percent. */
  cvcDiscountPct: number;
}

/** One voyage's cost, all figures in USD. */
export interface VoyageCost {
  index: number;
  label: string;
  departureDay: number;
  rateUsdPerMt: number;
  freight: number;
  bunker: number;
  portCharges: number;
  demurrage: number;
  lighterage: number;
  total: number;
}

export interface LighterageAssessment {
  required: boolean;
  reason: string;
  tonnesToLighten: number;
  extraDays: number;
  costPerVoyageUsd: number;
}

export interface Feasibility {
  blocked: boolean;
  reason: string;
}

export interface VoyageProfile {
  distanceNm: number;
  seaDays: number;
  cargoDays: number;
  waitDaysSpot: number;
  waitDaysCvc: number;
  roundTripDays: number;
  bunkerTonnes: number;
}

export interface CostSide {
  voyages: VoyageCost[];
  freightUsd: number;
  nonFreightUsd: number;
  totalUsd: number;
  totalCr: number;
  avgRateUsdPerMt: number;
}

export interface LineItem {
  label: string;
  spotCr: number;
  cvcCr: number;
  note?: string;
}

export interface CvcResult {
  inputs: CvcInputs;
  loadPortName: string;
  dischargePortName: string;
  profile: VoyageProfile;
  lighterage: LighterageAssessment;
  feasibility: Feasibility;
  /** Today's market rate the CVC is negotiated off, USD/MT. */
  marketRateUsdPerMt: number;
  /** The locked CVC rate, USD/MT. */
  lockedRateUsdPerMt: number;
  spot: CostSide;
  cvc: CostSide;
  lineItems: LineItem[];
  /** Spot total minus CVC total, INR crores. Positive means CVC is cheaper. */
  deltaCr: number;
  deltaPct: number;
  /** The average spot rate at which the two programmes cost the same, USD/MT. */
  breakEvenUsdPerMt: number;
  /** Probability the realised average spot rate lands the other side of break-even. */
  probSpotWins: number;
  /** Forecast mean and dispersion of the programme-average spot rate. */
  rateDistribution: { mean: number; sd: number };
  /** Delta at the floor and ceiling of the forecast's 90% band, INR crores. */
  band: {
    lowDeltaCr: number;
    highDeltaCr: number;
    lowAvgRate: number;
    highAvgRate: number;
  };
  headline: string;
  cvcWins: boolean;
}

// ─── Small maths helpers ──────────────────────────────────────────────────────

/** Great-circle distance in nautical miles. */
function haversineNm(aLat: number, aLng: number, bLat: number, bLng: number): number {
  const R = 3440.065; // Earth radius in nautical miles
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(bLat - aLat);
  const dLng = toRad(bLng - aLng);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(aLat)) * Math.cos(toRad(bLat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

/**
 * A great circle runs through land. Bulk routes to the East Coast of India
 * detour round capes and through straits, so the sailed distance runs above the
 * direct line by roughly this much.
 */
const ROUTING_FACTOR = 1.18;

/** Abramowitz & Stegun 7.1.26 error function, good to ~1.5e-7. */
function erf(x: number): number {
  const sign = x < 0 ? -1 : 1;
  const z = Math.abs(x);
  const t = 1 / (1 + 0.3275911 * z);
  const y =
    1 -
    ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) *
      t *
      Math.exp(-z * z);
  return sign * y;
}

/** Standard normal cumulative distribution. */
export function normalCdf(z: number): number {
  return 0.5 * (1 + erf(z / Math.SQRT2));
}

/** Standard normal probability density. */
export function normalPdf(z: number): number {
  return Math.exp(-0.5 * z * z) / Math.sqrt(2 * Math.PI);
}

// ─── Constraint engine hooks ──────────────────────────────────────────────────

/**
 * Laden draft scales with how much of the vessel's deadweight is actually used,
 * so a part cargo floats higher and may clear a berth a full cargo cannot.
 */
function ladenDraftAt(vesselClass: VesselClass, cargoTonnes: number): number {
  const spec = VESSEL_SPECS[vesselClass];
  const utilisation = Math.max(0, Math.min(1, cargoTonnes / spec.dwt.max));
  return spec.ballastDraftM + (spec.ladenDraftM - spec.ballastDraftM) * utilisation;
}

/**
 * Decide whether cargo has to come off at an anchorage before the ship can
 * berth, and how much. Tonnes per centimetre immersion converts the draft
 * shortfall straight into tonnes that must be transhipped.
 */
export function assessLighterage(
  port: Port,
  vesselClass: VesselClass,
  cargoTonnes: number,
): LighterageAssessment {
  const draft = ladenDraftAt(vesselClass, cargoTonnes);
  const permissible = port.currentDraftM - UKC_MARGIN_M;
  const shortfallM = draft - permissible;

  const none: LighterageAssessment = {
    required: false,
    reason: `${vesselClass} floats at ${draft.toFixed(1)} m on ${cargoTonnes.toLocaleString('en-IN')} T — inside ${port.name}'s ${permissible.toFixed(1)} m permissible draft.`,
    tonnesToLighten: 0,
    extraDays: 0,
    costPerVoyageUsd: 0,
  };

  if (shortfallM <= 0 && !port.lighterageRequired) return none;

  // Anchorage ports carry a mandatory transhipment even when draft clears.
  const byShortfall = Math.max(0, shortfallM) * 100 * TONNES_PER_CM[vesselClass];
  const mandatoryFloor = port.lighterageRequired ? cargoTonnes * 0.35 : 0;
  const tonnesToLighten = Math.min(cargoTonnes * 0.9, Math.max(byShortfall, mandatoryFloor));

  if (tonnesToLighten <= 0) return none;

  const extraDays = (tonnesToLighten / 25_000) * LIGHTERAGE_DAYS_PER_25KT;
  const costPerVoyageUsd = tonnesToLighten * LIGHTERAGE_USD_PER_MT + LIGHTERAGE_MOB_USD;

  const reason = port.lighterageRequired
    ? `${port.name} is an anchorage — ${Math.round(tonnesToLighten).toLocaleString('en-IN')} T must be transhipped to barges before the balance moves upriver.`
    : `${vesselClass} floats at ${draft.toFixed(1)} m against ${port.name}'s ${permissible.toFixed(1)} m permissible draft — ${shortfallM.toFixed(1)} m over, so ${Math.round(tonnesToLighten).toLocaleString('en-IN')} T lightens at Sagar/Sandheads.`;

  return { required: true, reason, tonnesToLighten, extraDays, costPerVoyageUsd };
}

function assessFeasibility(port: Port, vesselClass: VesselClass): Feasibility {
  const spec = VESSEL_SPECS[vesselClass];
  if (spec.loaM > port.maxLoaM) {
    return {
      blocked: true,
      reason: `${vesselClass} is ${spec.loaM} m LOA against ${port.name}'s ${port.maxLoaM} m limit. Length cannot be lightered away — this programme needs a smaller class.`,
    };
  }
  return { blocked: false, reason: '' };
}

// ─── Voyage profile ───────────────────────────────────────────────────────────

function buildProfile(
  loadPortId: string,
  dischargePort: Port,
  vesselClass: VesselClass,
  cargoTonnes: number,
  lighterage: LighterageAssessment,
): VoyageProfile {
  const spec = VESSEL_SPECS[vesselClass];
  const load = LOADING_PORTS.find(p => p.id === loadPortId);
  const loadTerms = LOAD_PORT_TERMS[loadPortId] ?? DEFAULT_LOAD_TERMS;

  const directNm = load
    ? haversineNm(load.lat, load.lng, dischargePort.lat, dischargePort.lng)
    : 4_000;
  const distanceNm = directNm * ROUTING_FACTOR;

  // Laden out, ballast home.
  const legDays = distanceNm / (spec.speedKts * 24);
  const seaDays = legDays * 2;

  const dischargeRate = dischargePort.cargoRateTpd > 0 ? dischargePort.cargoRateTpd : 15_000;
  const cargoDays = cargoTonnes / loadTerms.loadRateTpd + cargoTonnes / dischargeRate;

  const waitDaysSpot = SPOT_WAIT_DAYS[dischargePort.congestionLevel];
  const waitDaysCvc = waitDaysSpot * (1 - CVC_WAIT_REDUCTION);

  const roundTripDays =
    seaDays + cargoDays + waitDaysSpot + FIXED_TURNAROUND_DAYS + lighterage.extraDays;

  const bunkerTonnes =
    legDays * BUNKER_LADEN_TPD[vesselClass] +
    legDays * BUNKER_LADEN_TPD[vesselClass] * BALLAST_BURN_FACTOR +
    (cargoDays + waitDaysSpot + FIXED_TURNAROUND_DAYS + lighterage.extraDays) * BUNKER_PORT_TPD;

  return { distanceNm, seaDays, cargoDays, waitDaysSpot, waitDaysCvc, roundTripDays, bunkerTonnes };
}

// ─── The evaluation ───────────────────────────────────────────────────────────

export function evaluate(inputs: CvcInputs): CvcResult {
  const {
    loadPortId,
    dischargePortId,
    vesselClass,
    cargoTonnes,
    numVoyages,
    bunkerPriceUsd,
    demurrageUsdPerDay,
    cvcDiscountPct,
  } = inputs;

  const dischargePort = DISCHARGE_PORTS.find(p => p.id === dischargePortId) ?? DISCHARGE_PORTS[0];
  const loadPort = LOADING_PORTS.find(p => p.id === loadPortId) ?? LOADING_PORTS[0];

  const lighterage = assessLighterage(dischargePort, vesselClass, cargoTonnes);
  const feasibility = assessFeasibility(dischargePort, vesselClass);
  const profile = buildProfile(loadPortId, dischargePort, vesselClass, cargoTonnes, lighterage);

  // ── Terms that do not move with the freight rate ───────────────────────────
  const loadTerms = LOAD_PORT_TERMS[loadPortId] ?? DEFAULT_LOAD_TERMS;
  const dischargeTerms = DISCHARGE_PORT_CHARGES[dischargePortId] ?? DEFAULT_DISCHARGE_CHARGE;
  const portChargesUsd =
    loadTerms.perMtUsd * cargoTonnes +
    loadTerms.callUsd +
    dischargeTerms.perMtUsd * cargoTonnes +
    dischargeTerms.callUsd;

  const demurrageSpotUsd = profile.waitDaysSpot * demurrageUsdPerDay;
  const demurrageCvcUsd = profile.waitDaysCvc * demurrageUsdPerDay;

  // Freight already covers the owner's bunkers, so this line carries only the
  // deviation from the market's bunker basis. The CVC's clause hedges most of
  // that move, and only the unhedged share reaches the charterer.
  const bunkerDeviationUsd = profile.bunkerTonnes * (bunkerPriceUsd - BUNKER_BASIS_USD);
  const bunkerSpotUsd = bunkerDeviationUsd;
  const bunkerCvcUsd = bunkerDeviationUsd * (1 - CVC_BAF_HEDGE);

  const lighterageUsd = lighterage.costPerVoyageUsd;

  // ── Rates ──────────────────────────────────────────────────────────────────
  // Voyage i departs one round trip after voyage i-1 and is priced at the
  // forecast for that departure. Both programmes share the same schedule, so
  // the comparison holds everything but the rate constant.
  const outlooks: RateOutlook[] = [];
  for (let i = 0; i < numVoyages; i++) {
    outlooks.push(getRateOutlook(vesselClass, Math.round(i * profile.roundTripDays)));
  }

  const marketRateUsdPerMt = getCurrentSpotRate(vesselClass);
  const lockedRateUsdPerMt = marketRateUsdPerMt * (1 - cvcDiscountPct / 100);

  // ── Build both sides ───────────────────────────────────────────────────────
  const buildSide = (
    rateFor: (i: number) => number,
    bunker: number,
    demurrage: number,
  ): CostSide => {
    const voyages: VoyageCost[] = outlooks.map((o, i) => {
      const rate = rateFor(i);
      const freight = rate * cargoTonnes;
      return {
        index: i + 1,
        label: o.label,
        departureDay: o.dayOffset,
        rateUsdPerMt: rate,
        freight,
        bunker,
        portCharges: portChargesUsd,
        demurrage,
        lighterage: lighterageUsd,
        total: freight + bunker + portChargesUsd + demurrage + lighterageUsd,
      };
    });
    const freightUsd = voyages.reduce((s, v) => s + v.freight, 0);
    const nonFreightUsd = voyages.reduce(
      (s, v) => s + v.bunker + v.portCharges + v.demurrage + v.lighterage,
      0,
    );
    const totalUsd = freightUsd + nonFreightUsd;
    return {
      voyages,
      freightUsd,
      nonFreightUsd,
      totalUsd,
      totalCr: usdToCrore(totalUsd),
      avgRateUsdPerMt: voyages.reduce((s, v) => s + v.rateUsdPerMt, 0) / Math.max(1, voyages.length),
    };
  };

  const spot = buildSide(i => outlooks[i].mean, bunkerSpotUsd, demurrageSpotUsd);
  const cvc = buildSide(() => lockedRateUsdPerMt, bunkerCvcUsd, demurrageCvcUsd);

  const deltaCr = spot.totalCr - cvc.totalCr;
  const deltaPct = spot.totalCr !== 0 ? (deltaCr / spot.totalCr) * 100 : 0;

  // ── Break-even ─────────────────────────────────────────────────────────────
  // The average spot rate R* that makes the two programmes cost the same:
  //   R* x tonnage x N + spot non-freight = CVC total
  const breakEvenUsdPerMt =
    (cvc.totalUsd - spot.nonFreightUsd) / Math.max(1, cargoTonnes * numVoyages);

  // ── How likely is the forecast wrong enough to matter ──────────────────────
  const mean = spot.avgRateUsdPerMt;
  const sdPerVoyage =
    outlooks.reduce((s, o) => s + (o.upper - o.lower) / (2 * BAND_Z), 0) / Math.max(1, numVoyages);
  // Errors travel together across months, so averaging N voyages shrinks the
  // dispersion by far less than 1/sqrt(N).
  const sd =
    sdPerVoyage *
    Math.sqrt((1 + (numVoyages - 1) * RATE_ERROR_CORRELATION) / Math.max(1, numVoyages));

  const cvcWins = deltaCr >= 0;
  // Spot wins when the realised average rate lands below break-even.
  const probSpotWins = sd > 0 ? normalCdf((breakEvenUsdPerMt - mean) / sd) : cvcWins ? 0 : 1;

  // ── Upside / downside at the edges of the forecast band ────────────────────
  const lowAvgRate = outlooks.reduce((s, o) => s + o.lower, 0) / Math.max(1, numVoyages);
  const highAvgRate = outlooks.reduce((s, o) => s + o.upper, 0) / Math.max(1, numVoyages);
  const spotTotalAt = (avgRate: number) =>
    usdToCrore(avgRate * cargoTonnes * numVoyages + spot.nonFreightUsd);
  const lowDeltaCr = spotTotalAt(lowAvgRate) - cvc.totalCr;
  const highDeltaCr = spotTotalAt(highAvgRate) - cvc.totalCr;

  // ── Line items ─────────────────────────────────────────────────────────────
  const lineItems: LineItem[] = [
    {
      label: 'Base freight',
      spotCr: usdToCrore(spot.freightUsd),
      cvcCr: usdToCrore(cvc.freightUsd),
      note: `$${spot.avgRateUsdPerMt.toFixed(2)}/T average forecast vs $${lockedRateUsdPerMt.toFixed(2)}/T locked`,
    },
    {
      label: 'Bunker adjustment',
      spotCr: usdToCrore(bunkerSpotUsd * numVoyages),
      cvcCr: usdToCrore(bunkerCvcUsd * numVoyages),
      note: `${Math.round(profile.bunkerTonnes)} T VLSFO burnt per voyage · deviation from the $${BUNKER_BASIS_USD}/T basis, ${Math.round(CVC_BAF_HEDGE * 100)}% hedged under the CVC`,
    },
    {
      label: 'Port charges',
      spotCr: usdToCrore(portChargesUsd * numVoyages),
      cvcCr: usdToCrore(portChargesUsd * numVoyages),
      note: `${loadPort.name} load + ${dischargePort.name} discharge, identical either way`,
    },
    {
      label: 'Expected demurrage',
      spotCr: usdToCrore(demurrageSpotUsd * numVoyages),
      cvcCr: usdToCrore(demurrageCvcUsd * numVoyages),
      note: `${profile.waitDaysSpot.toFixed(1)} d expected wait on spot vs ${profile.waitDaysCvc.toFixed(1)} d on a nominated berth window`,
    },
    {
      label: 'Lighterage',
      spotCr: usdToCrore(lighterageUsd * numVoyages),
      cvcCr: usdToCrore(lighterageUsd * numVoyages),
      note: lighterage.required ? lighterage.reason : 'Not flagged — draft clears without transhipment',
    },
  ];

  return {
    inputs,
    loadPortName: loadPort.name,
    dischargePortName: dischargePort.name,
    profile,
    lighterage,
    feasibility,
    marketRateUsdPerMt,
    lockedRateUsdPerMt,
    spot,
    cvc,
    lineItems,
    deltaCr,
    deltaPct,
    breakEvenUsdPerMt,
    probSpotWins,
    rateDistribution: { mean, sd },
    band: { lowDeltaCr, highDeltaCr, lowAvgRate, highAvgRate },
    headline: buildHeadline({
      cvcWins,
      deltaCr,
      numVoyages,
      breakEvenUsdPerMt,
      probSpotWins,
    }),
    cvcWins,
  };
}

// ─── Headline ─────────────────────────────────────────────────────────────────

function formatCr(cr: number): string {
  const abs = Math.abs(cr);
  return abs >= 10 ? abs.toFixed(1) : abs.toFixed(2);
}

function buildHeadline(a: {
  cvcWins: boolean;
  deltaCr: number;
  numVoyages: number;
  breakEvenUsdPerMt: number;
  probSpotWins: number;
}): string {
  const voyages = `${a.numVoyages} voyage${a.numVoyages === 1 ? '' : 's'}`;
  const be = `$${a.breakEvenUsdPerMt.toFixed(2)}/T`;

  if (a.cvcWins) {
    return `CVC saves ₹${formatCr(a.deltaCr)} Cr across ${voyages}. Spot only wins if rates fall below ${be} — our forecast puts that probability at ${Math.round(a.probSpotWins * 100)}%.`;
  }
  return `Spot beats CVC by ₹${formatCr(a.deltaCr)} Cr across ${voyages}. The lock only pays if rates hold above ${be} — our forecast puts that probability at ${Math.round((1 - a.probSpotWins) * 100)}%.`;
}

// ─── Chart data ───────────────────────────────────────────────────────────────

export interface CumulativePoint {
  voyage: string;
  spot: number;
  cvc: number;
  spotLow: number;
  spotHigh: number;
  /** [low, high] pair recharts draws the band from. */
  spotBand: [number, number];
  monthLabel: string;
}

/** Cumulative programme cost after each voyage, INR crores. */
export function cumulativeSeries(r: CvcResult): CumulativePoint[] {
  const { cargoTonnes } = r.inputs;
  const out: CumulativePoint[] = [];
  let spot = 0;
  let cvc = 0;
  let low = 0;
  let high = 0;

  r.spot.voyages.forEach((v, i) => {
    const cvcVoyage = r.cvc.voyages[i];
    const nonFreight = v.bunker + v.portCharges + v.demurrage + v.lighterage;
    const outlookLow = r.band.lowAvgRate;
    const outlookHigh = r.band.highAvgRate;

    spot += usdToCrore(v.total);
    cvc += usdToCrore(cvcVoyage.total);
    low += usdToCrore(outlookLow * cargoTonnes + nonFreight);
    high += usdToCrore(outlookHigh * cargoTonnes + nonFreight);

    out.push({
      voyage: `V${v.index}`,
      monthLabel: v.label,
      spot: +spot.toFixed(3),
      cvc: +cvc.toFixed(3),
      spotLow: +low.toFixed(3),
      spotHigh: +high.toFixed(3),
      spotBand: [+low.toFixed(3), +high.toFixed(3)],
    });
  });

  return out;
}

export interface DensityPoint {
  rate: number;
  /** Density where spot comes out cheaper; null elsewhere so the area stops. */
  spotWins: number | null;
  /** Density where the lock comes out cheaper. */
  cvcWins: number | null;
}

/**
 * The forecast's distribution for the programme-average spot rate, split at the
 * break-even. The area under `spotWins` is the probability spot beats the lock.
 */
export function breakEvenDensity(r: CvcResult, steps = 96): DensityPoint[] {
  const { mean, sd } = r.rateDistribution;
  if (sd <= 0) return [];

  const from = Math.min(mean - 3.4 * sd, r.breakEvenUsdPerMt - 0.6 * sd);
  const to = Math.max(mean + 3.4 * sd, r.breakEvenUsdPerMt + 0.6 * sd);
  const step = (to - from) / steps;
  const be = r.breakEvenUsdPerMt;

  const points: DensityPoint[] = [];
  for (let i = 0; i <= steps; i++) {
    const rate = from + step * i;
    const d = normalPdf((rate - mean) / sd) / sd;
    points.push({
      rate: +rate.toFixed(3),
      spotWins: rate <= be ? +d.toFixed(6) : null,
      cvcWins: rate >= be ? +d.toFixed(6) : null,
    });
  }

  // Pin an exact sample at the break-even so the two areas meet without a gap.
  const dBe = normalPdf((be - mean) / sd) / sd;
  points.push({ rate: +be.toFixed(3), spotWins: +dBe.toFixed(6), cvcWins: +dBe.toFixed(6) });
  points.sort((a, b) => a.rate - b.rate);

  return points;
}
