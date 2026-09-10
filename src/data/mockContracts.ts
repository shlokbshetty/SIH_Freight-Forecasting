// ─── Default programme for the Spot vs CVC evaluator ──────────────────────────
// The costing itself lives in src/lib/cvcEngine.ts and is driven entirely by
// ports.ts, vessels.ts, the forecast series and costAssumptions.ts. This file
// only supplies the programme the page opens on, plus a few saved shapes.

import type { CvcInputs } from '../lib/cvcEngine';
import { DEFAULT_DEMURRAGE_USD_PER_DAY, BUNKER_BASIS_USD } from './costAssumptions';

export const DEFAULT_PROGRAMME: CvcInputs = {
  loadPortId: 'newcastle',
  dischargePortId: 'paradip',
  vesselClass: 'Supramax',
  cargoTonnes: 55_000,
  numVoyages: 4,
  bunkerPriceUsd: BUNKER_BASIS_USD,
  demurrageUsdPerDay: DEFAULT_DEMURRAGE_USD_PER_DAY,
  cvcDiscountPct: 5,
};

export interface ProgrammePreset {
  id: string;
  label: string;
  hint: string;
  inputs: CvcInputs;
}

/** Shapes that exercise the constraint engine as well as the rate model. */
export const PROGRAMME_PRESETS: ProgrammePreset[] = [
  {
    id: 'newcastle-paradip',
    label: 'Newcastle → Paradip',
    hint: 'Supramax · 4 voyages · clears on draft',
    inputs: DEFAULT_PROGRAMME,
  },
  {
    id: 'gladstone-gangavaram',
    label: 'Gladstone → Gangavaram',
    hint: 'Panamax · 6 voyages · deep-water berth',
    inputs: {
      ...DEFAULT_PROGRAMME,
      loadPortId: 'gladstone',
      dischargePortId: 'gangavaram',
      vesselClass: 'Panamax',
      cargoTonnes: 72_000,
      numVoyages: 6,
    },
  },
  {
    id: 'kalimantan-haldia',
    label: 'Kalimantan → Haldia',
    hint: 'Panamax · lighterage at Sagar/Sandheads',
    inputs: {
      ...DEFAULT_PROGRAMME,
      loadPortId: 'kalimantan',
      dischargePortId: 'haldia',
      vesselClass: 'Panamax',
      cargoTonnes: 68_000,
      numVoyages: 4,
    },
  },
  {
    id: 'beira-vizag',
    label: 'Beira → Vizag',
    hint: 'Handysize · 5 voyages · slow load port',
    inputs: {
      ...DEFAULT_PROGRAMME,
      loadPortId: 'beira',
      dischargePortId: 'vizag',
      vesselClass: 'Handysize',
      cargoTonnes: 35_000,
      numVoyages: 5,
    },
  },
];
