// ─── Contract Comparison Mock Data ───────────────────────────────────────────

export interface ContractLineItem {
  label: string;
  spot: number;    // INR Crores
  cvc: number;     // INR Crores
}

export interface ContractScenario {
  id: string;
  route: string;             // e.g. "Newcastle → Paradip"
  vesselClass: string;
  cargoTonnes: number;
  numVoyages: number;        // number of spot voyages vs 1 CVC
  spotRate: number;          // USD / MT
  cvcRate: number;           // USD / MT (negotiated)
  bunkerPrice: number;       // USD / MT (default slider value)
  cvcDiscount: number;       // % discount on CVC vs spot
  lineItems: ContractLineItem[];
  verdictSummary: string;
  breakEvenRate: number;     // USD/MT at which spot == CVC
  confidencePct: number;     // probability spot wins
}

export const MOCK_CONTRACT_SCENARIO: ContractScenario = {
  id: 'newcastle-paradip-supramax',
  route: 'Newcastle → Paradip',
  vesselClass: 'Supramax',
  cargoTonnes: 200000,
  numVoyages: 4,
  spotRate: 18.4,
  cvcRate: 15.8,
  bunkerPrice: 620,
  cvcDiscount: 14.1,
  lineItems: [
    { label: 'Base Freight',         spot: 6.78,  cvc: 5.82 },
    { label: 'Bunker Adjustment',    spot: 1.24,  cvc: 1.10 },
    { label: 'Port Charges',         spot: 0.88,  cvc: 0.88 },
    { label: 'Expected Demurrage',   spot: 0.62,  cvc: 0.30 },
    { label: 'Lighterage',           spot: 0.00,  cvc: 0.00 },
  ],
  verdictSummary: 'CVC saves ₹4.2 Cr · break-even $18.40/T · 22% chance spot wins',
  breakEvenRate: 18.4,
  confidencePct: 22,
};

// Stacked spot segment heights (simulate volatility visually)
export const MOCK_SPOT_SEGMENTS = [
  { voyage: 1, rateDelta: +1.2 },
  { voyage: 2, rateDelta: -0.4 },
  { voyage: 3, rateDelta: +2.1 },
  { voyage: 4, rateDelta: -0.8 },
];
