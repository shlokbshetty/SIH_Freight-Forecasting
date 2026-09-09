// ─── Vessel Classes ────────────────────────────────────────────────────────────

export type VesselClass = 'Handysize' | 'Supramax' | 'Panamax' | 'Capesize';

export interface VesselSpec {
  class: VesselClass;
  dwt: { min: number; max: number };     // Deadweight tonnage range (tonnes)
  loaM: number;                           // Length Overall (metres, typical max)
  beamM: number;                          // Beam (metres)
  ladenDraftM: number;                    // Laden draft (metres, typical)
  ballastDraftM: number;                  // Ballast draft (metres)
  speedKts: number;                       // Service speed (knots)
  color: string;                          // Chart / map colour
  description: string;
}

export const VESSEL_SPECS: Record<VesselClass, VesselSpec> = {
  Handysize: {
    class: 'Handysize',
    dwt: { min: 28000, max: 40000 },
    loaM: 190,
    beamM: 28,
    ladenDraftM: 10.0,
    ballastDraftM: 7.5,
    speedKts: 14,
    color: '#22c55e',
    description: 'Smallest bulk carrier. Fits virtually all East Coast ports including Gopalpur & Haldia.',
  },
  Supramax: {
    class: 'Supramax',
    dwt: { min: 50000, max: 60000 },
    loaM: 200,
    beamM: 32,
    ladenDraftM: 12.8,
    ballastDraftM: 9.0,
    speedKts: 13.5,
    color: '#3b82f6',
    description: 'Workhorse of bulk trade. Good fit for Paradip, Dhamra, Gangavaram. Tight on Haldia.',
  },
  Panamax: {
    class: 'Panamax',
    dwt: { min: 65000, max: 80000 },
    loaM: 229,
    beamM: 32.3,
    ladenDraftM: 14.0,
    ballastDraftM: 9.5,
    speedKts: 13,
    color: '#f59e0b',
    description: 'Constrained at Haldia & Gopalpur. May require partial lighterage at Sagar/Sandheads.',
  },
  Capesize: {
    class: 'Capesize',
    dwt: { min: 100000, max: 180000 },
    loaM: 300,
    beamM: 50,
    ladenDraftM: 17.5,
    ballastDraftM: 11.5,
    speedKts: 14.5,
    color: '#ef4444',
    description: 'Largest class. Only Gangavaram & Vizag deep-water capable. Lighterage required for Haldia.',
  },
};

export const VESSEL_CLASSES: VesselClass[] = ['Handysize', 'Supramax', 'Panamax', 'Capesize'];
