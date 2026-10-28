# FreightIQ Product Roadmap

This roadmap outlines planned engineering, econometric, and operational milestones for **FreightIQ** (`SIH_Freight-Forecasting`).

---

## Short-Term Milestones (v0.3 — Next 1–2 Quarters)

### 1. Full Frontend Rewiring to Berth-Level & Live Series Endpoints
- **Current State**: Several React views (`src/data/ports.ts`, `src/data/vessels.ts`, `src/lib/cvcEngine.ts`) maintain parallel static reference tables alongside `src/lib/fallbacks.ts`.
- **Target**: Wire all 10 React pages directly to `GET /api/ports`, `POST /api/match`, `POST /api/contract`, and `GET /api/series` as their primary source of truth, retaining `src/data/` strictly as the offline fallback snapshot.

### 2. Automated CI Test Guard for `OWN_DRIVER` vs. `CLASS_DRIVERS`
- **Current State**: `models/project.py:OWN_DRIVER` and `data/ingest.py:CLASS_DRIVERS` are coupled by convention.
- **Target**: Add a dedicated assertion in `backend/tests/test_invariants.py` that imports both dictionaries and verifies exact 1-to-1 alignment on every commit.

### 3. Interactive Multi-Port Split Visualizer in `ContractComparison.tsx`
- **Current State**: `POST /api/contract/multiport` computes optimal two-port parcel splits (e.g., Gangavaram + Haldia) on the backend.
- **Target**: Expose a dedicated two-port split tab in `ContractComparison.tsx` and `Map.tsx` showing draft reduction after the first discharge call vs. Sandheads lighterage cost.

---

## Medium-Term Milestones (v0.4 — 3–4 Quarters)

### 4. Hybrid Ensemble Combining Log-SARIMAX with Quantile Gradient Boosting
- Combine the structural interpretability and exogenous scenario hooks of `backend/models/project.py` (SARIMAX) with the route-specific non-linear quantile models (`p10`/`p50`/`p90` `.joblib` models in `data/historical/models/` and `engine/ml_forecaster.py`) via inverse-variance stacking.

### 5. Licensed Baltic & Live AIS Stream Drop-In Connectors
- Upgrade `BalticAdapter`, `BunkerAdapter`, and `AISAdapter` to support authenticated WebSocket/REST feeds from the Baltic Exchange, Argus/Platts bunker quotes, and Indian Ocean terrestrial/satellite AIS receivers without altering downstream cache schemas.

---

## Long-Term Milestones (v1.0+)

### 6. Fleet-Wide Linear Programming Stemming & Laycan Scheduler
- Extend single-programme evaluation into a multi-vessel, multi-cargo Mixed-Integer Linear Program (MILP) that jointly schedules laycans across all East Coast steel and thermal power plants while minimizing aggregate demurrage and ballast steaming days.
