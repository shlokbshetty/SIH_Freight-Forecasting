import { createContext, useContext, useState, type ReactNode } from 'react';
import type { VesselClass } from '../data/vessels';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface SelectedVessel {
  cls: VesselClass;
  originId: string;
  dischargeId: string;
  tonnage: number;
  commodity: string;
  targetMonth: string;
  estimatedCost: number;
}

export interface LockedCharter {
  id: string;
  vessel: string;
  cls: VesselClass;
  route: string;
  eta: string;
  badge: 'Locked' | 'En Route' | 'Berthed';
  cvcRate: number;   // USD/MT
  cargoTonnes: number;
  lockedAt: string;  // ISO timestamp
}

interface CharterStore {
  selectedVessel: SelectedVessel | null;
  setSelectedVessel: (v: SelectedVessel | null) => void;
  lockedCharters: LockedCharter[];
  lockCharter: (c: LockedCharter) => void;
}

// ─── Context ──────────────────────────────────────────────────────────────────

const CharterCtx = createContext<CharterStore | null>(null);

export function CharterProvider({ children }: { children: ReactNode }) {
  const [selectedVessel, setSelectedVessel] = useState<SelectedVessel | null>(null);
  const [lockedCharters, setLockedCharters] = useState<LockedCharter[]>([]);

  const lockCharter = (c: LockedCharter) =>
    setLockedCharters(prev => [c, ...prev]);

  return (
    <CharterCtx.Provider value={{ selectedVessel, setSelectedVessel, lockedCharters, lockCharter }}>
      {children}
    </CharterCtx.Provider>
  );
}

export function useCharter() {
  const ctx = useContext(CharterCtx);
  if (!ctx) throw new Error('useCharter must be used inside CharterProvider');
  return ctx;
}
