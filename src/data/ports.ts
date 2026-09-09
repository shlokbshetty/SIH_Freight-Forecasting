// ─── East Coast Indian Discharge Ports ────────────────────────────────────────

export type PortStatus = 'available' | 'constrained' | 'blocked';

export interface Port {
  id: string;
  name: string;
  lat: number;
  lng: number;
  maxDraftM: number;          // metres
  currentDraftM: number;      // metres (tide-adjusted, mock)
  maxLoaM: number;            // metres
  berthCount: number;
  berthsAvailable: number;
  cargoRateTpd: number;       // tons per day discharge rate
  lighterageRequired: boolean;
  congestionLevel: 'low' | 'medium' | 'high';
  notes?: string;
}

export const DISCHARGE_PORTS: Port[] = [
  {
    id: 'paradip',
    name: 'Paradip',
    lat: 20.2649, lng: 86.6800,
    maxDraftM: 14.5, currentDraftM: 14.0,
    maxLoaM: 270, berthCount: 8, berthsAvailable: 3,
    cargoRateTpd: 35000, lighterageRequired: false,
    congestionLevel: 'medium',
  },
  {
    id: 'vizag',
    name: 'Visakhapatnam (Vizag)',
    lat: 17.6868, lng: 83.2185,
    maxDraftM: 16.0, currentDraftM: 15.5,
    maxLoaM: 300, berthCount: 12, berthsAvailable: 5,
    cargoRateTpd: 45000, lighterageRequired: false,
    congestionLevel: 'low',
  },
  {
    id: 'gangavaram',
    name: 'Gangavaram',
    lat: 17.6260, lng: 83.2280,
    maxDraftM: 18.5, currentDraftM: 18.0,
    maxLoaM: 350, berthCount: 6, berthsAvailable: 2,
    cargoRateTpd: 50000, lighterageRequired: false,
    congestionLevel: 'low',
  },
  {
    id: 'gopalpur',
    name: 'Gopalpur',
    lat: 19.2600, lng: 84.9100,
    maxDraftM: 10.5, currentDraftM: 9.8,
    maxLoaM: 190, berthCount: 3, berthsAvailable: 1,
    cargoRateTpd: 18000, lighterageRequired: false,
    congestionLevel: 'medium',
    notes: 'Shallow port — Handysize only at high tide',
  },
  {
    id: 'dhamra',
    name: 'Dhamra',
    lat: 20.4717, lng: 86.8981,
    maxDraftM: 17.0, currentDraftM: 16.5,
    maxLoaM: 320, berthCount: 4, berthsAvailable: 2,
    cargoRateTpd: 40000, lighterageRequired: false,
    congestionLevel: 'low',
  },
  {
    id: 'sagar-sandheads',
    name: 'Sagar / Sandheads',
    lat: 21.6400, lng: 88.0600,
    maxDraftM: 8.5, currentDraftM: 8.0,
    maxLoaM: 160, berthCount: 0, berthsAvailable: 0,
    cargoRateTpd: 0, lighterageRequired: true,
    congestionLevel: 'high',
    notes: 'Anchorage / lighterage point. Capesize / Panamax must lighten here before proceeding to Haldia.',
  },
  {
    id: 'haldia',
    name: 'Haldia',
    lat: 22.0257, lng: 88.1015,
    maxDraftM: 8.2, currentDraftM: 7.9,
    maxLoaM: 170, berthCount: 7, berthsAvailable: 2,
    cargoRateTpd: 20000, lighterageRequired: false,
    congestionLevel: 'high',
    notes: 'Tidal window critical. River approach — strict LOA & draft limits.',
  },
];

// ─── Loading Ports (Origin) ────────────────────────────────────────────────────

export interface LoadingPort {
  id: string;
  name: string;
  country: string;
  lat: number;
  lng: number;
  commodities: string[];
}

export const LOADING_PORTS: LoadingPort[] = [
  { id: 'newcastle', name: 'Newcastle', country: 'Australia', lat: -32.9283, lng: 151.7817, commodities: ['Coal'] },
  { id: 'gladstone', name: 'Gladstone', country: 'Australia', lat: -23.8427, lng: 151.2580, commodities: ['Coal', 'Bauxite'] },
  { id: 'abbot-point', name: 'Abbot Point', country: 'Australia', lat: -19.8800, lng: 148.0900, commodities: ['Coal'] },
  { id: 'hampton-roads', name: 'Hampton Roads', country: 'USA', lat: 36.9460, lng: -76.3200, commodities: ['Coal'] },
  { id: 'beira', name: 'Beira', country: 'Mozambique', lat: -19.8436, lng: 34.8380, commodities: ['Coal'] },
  { id: 'nacala', name: 'Nacala', country: 'Mozambique', lat: -14.5480, lng: 40.6820, commodities: ['Coal'] },
  { id: 'murmansk', name: 'Murmansk', country: 'Russia', lat: 68.9585, lng: 33.0827, commodities: ['Coal'] },
  { id: 'kalimantan', name: 'Kalimantan', country: 'Indonesia', lat: -1.6815, lng: 116.3690, commodities: ['Coal'] },
  { id: 'balikpapan', name: 'Balikpapan', country: 'Indonesia', lat: -1.2675, lng: 116.8289, commodities: ['Coal', 'Palm Oil'] },
];

// ─── Helper: compute port status vs vessel draft ───────────────────────────────

export function getPortStatus(port: Port, vesselLadenDraftM: number, vesselLoaM: number): PortStatus {
  if (vesselLadenDraftM > port.currentDraftM || vesselLoaM > port.maxLoaM) {
    return 'blocked';
  }
  const draftMargin = port.currentDraftM - vesselLadenDraftM;
  if (draftMargin < 1.0 || port.berthsAvailable === 0 || port.congestionLevel === 'high') {
    return 'constrained';
  }
  return 'available';
}
