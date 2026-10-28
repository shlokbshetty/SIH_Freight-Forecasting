# Changelog

All notable changes to **FreightIQ** (`SIH_Freight-Forecasting`) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [v0.2.0] - 2026-10-28

### Added
- **Log-Space SARIMAX Projection Engine (`backend/models/project.py`, `backend/train.py`)**:
  - Fitted per-class `SARIMAX(1, 1, 1)` models on `log(rate)` with z-scored exogenous regressors (`log_bdi`, `log_gogl`, `log_sblk`, `log_bunker`, `log_coal`, `log_iron_ore`, `log_usdinr`, `monsoon`, `month_sin`, `month_cos`).
  - Added Nelder-Mead simplex warm-start fallback (`_fit_with_warm_start`) when L-BFGS stalls on collinear regressors.
  - Added zero-refit request-time state-space Kalman filtering (`SARIMAXResults.apply(..., refit=False)`), dollar-per-tonne driver decomposition (`driver_contributions()`), what-if scenario overrides (`scenario`), and 4-fold rolling-origin backtesting (`rolling_origin_backtest()`).
- **Berth-Level Physical & Lighterage Resolver (`backend/data/ports/resolver.py`, `berths.csv`, `lighterage_nodes.csv`, `PROVENANCE.md`)**:
  - Replaced flat port-level draft checks with berth-by-berth resolution (`ACCEPT_ALL_TIDE`, `ACCEPT_HIGH_TIDE_ONLY`, `REJECT`) across Paradip, Visakhapatnam (outer vs. inner harbour), Gangavaram, Dhamra, Gopalpur, and Haldia.
  - Added automated lighterage planning (`LighteragePlan`) via Sandheads and Sagar anchorages using class immersion rates (`TONNES_PER_CM`).
- **Period Time Charter (`ptc`) & Multi-Port Split Cargo Optimiser (`backend/app/costing.py`, `backend/app/routers/contract.py`)**:
  - Added 3-way structure comparison (`spot` vs. `cvc` vs. `ptc`) in `POST /api/contract`.
  - Added `POST /api/contract/multiport` to evaluate splitting parcels across two discharge ports (e.g., Gangavaram + Haldia) to avoid barge lighterage.
- **Evaluate Compatibility Router (`backend/app/routers/evaluate.py`)**:
  - Added `GET /api/ports/catalog` and `POST /api/evaluate` translating uppercase evaluator codes (`PPA`, `HAY_POINT`, `PANAMAX`) to canonical backend models.
- **SQLite WAL Observation Cache & Offline Snapshot (`backend/data/cache.py`, `backend/data/snapshot.json`, `scripts/refresh_snapshot.py`, `scripts/generate_baseline_snapshot.py`)**:
  - Added cold-boot seeding (`ingest.bootstrap`), proxy disclosure flags (`is_proxy`, `source_label`), and raw metric query endpoints (`GET /api/series`, `GET /api/series/metrics`, `GET /api/data/status`, `POST /api/data/refresh`).
- **React 19 Operational Command Deck (`src/`)**:
  - Added 10 analytical pages (`CommandCenter`, `Map`, `Forecast`, `Matcher`, `ContractComparison`, `Evaluate`, `MarketTiming`, `IdlePlanner`, `RiskAlerts`, `VoyageEditor`) with `DataStatusProvider`, `ConnectionBadge`, `DataOriginNotice`, and 8-second timeout fallback switching (`src/lib/api.ts`, `src/lib/fallbacks.ts`).
- **Unified Process-Group Orchestrator (`run.sh`)**: Added single-script setup, CPython 3.12 detection, offline mode (`--offline`), model retraining (`--retrain`), and full test execution (`--test`).

### Changed
- Corrected per-tonne freight rate ordering in backend economics so economies of scale hold (`Capesize < Panamax < Supramax < Handysize` on a USD/tonne basis).
- Resampled sparse monthly macro/bunker series (`FRED coal`, `bunker_vlsfo.csv`) using time-based linear interpolation (`_densify`) rather than staircase forward-filling.

### Removed
- Excluded container liner equity `ZIM` from dry-bulk SARIMAX regressors (`FEATURES`) to prevent cross-sector noise contamination.

### Fixed
- Added `OWN_DRIVER` circularity guard in `backend/models/project.py` so each vessel class drops the proxy series that generated its synthetic target in `backend/data/ingest.py`.
