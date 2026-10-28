# FreightIQ System Architecture

![FreightIQ System Architecture Overview](docs/assets/system-overview.svg)

---

## 1. Visual Legend & System Boundaries

| Visual Layer / Color | Architectural Boundary | Key Modules & Files |
| :--- | :--- | :--- |
| **Sky Blue (`#0284c7`)** | **React 19 Command Deck (`src/`)** | `App.tsx`, `CommandCenter.tsx`, `Map.tsx`, `Forecast.tsx`, `Matcher.tsx`, `ContractComparison.tsx`, `Evaluate.tsx`, `MarketTiming.tsx`, `IdlePlanner.tsx`, `RiskAlerts.tsx`, `VoyageEditor.tsx`, `DataStatusProvider.tsx`, `ConnectionBadge.tsx`, `DataOriginNotice.tsx` |
| **Teal (`#0d9488`)** | **FastAPI Gateway & Routers (`backend/app/`)** | `main.py`, `config.py`, `deps.py`, `schemas.py`, `routers/ports.py`, `routers/match.py`, `routers/forecast.py`, `routers/contract.py`, `routers/evaluate.py`, `routers/series.py`, `routers/status.py` |
| **Violet (`#7c3aed`)** | **Quantitative ML, Costing & Berth Engines** | `backend/models/project.py`, `backend/app/costing.py`, `backend/app/rates.py`, `backend/data/ports/resolver.py`, `backend/data/ports/schema.py`, plus `engine/` (`ml_forecaster.py`, `financial_evaluator.py`, `breakeven_analyzer.py`, `voyage_cost.py`, `feasibility.py`) |
| **Magenta (`#db2777`)** | **Market & Weather Ingestion Adapters** | `backend/data/ingest.py`, `backend/data/adapters/` (`base.py`, `baltic.py`, `equity.py`, `commodity.py`, `macro.py`, `fred.py`, `bunker.py`, `congestion.py`, `weather.py`, `ais.py`) |
| **Amber (`#d97706`)** | **SQLite WAL Cache & Model Artifacts** | `backend/data/cache.py` (`cache.db`), `backend/data/snapshot.json`, `backend/data/ports/berths.csv`, `backend/data/ports/lighterage_nodes.csv`, `backend/models/metrics.json`, `backend/models/sarimax_*.pkl`, `data/historical/*.parquet` |

---

## 2. Core Architectural Principles & Design Patterns

### 2.1 Zero Network Calls on the Request Path
No FastAPI request handler ever makes an outbound HTTP call or fits a statistical model:
1. Background ingestion (`APScheduler` running `ingest.refresh_all()` every 60 minutes) pulls external market and weather adapters through `SourceAdapter.safe_fetch()` and writes rows to SQLite (`cache.db` in WAL mode).
2. On cold boot, `ingest.bootstrap()` checks if `cache.db` is empty and automatically seeds it from the committed `backend/data/snapshot.json`.
3. Request handlers read exclusively from `cache.db`, pre-loaded `ProjectionBundle` pickles (`state.bundles`), and committed CSV/JSON reference files.

### 2.2 Log-Space SARIMAX with State-Space Kalman Filtering (`backend/models/project.py`)
- **Multiplicative Log-Space Formulation**: Freight rates are strictly positive and exhibit right-skewed spikes. Fitting `SARIMAX(1, 1, 1)` on `log(rate)` prevents lower prediction intervals (`p80`, `p95`) from crossing zero at 90- and 180-day horizons and makes exogenous coefficients interpretable as elasticities.
- **Fourier Seasonality + Monsoon Step**: Rather than an intractable `seasonal_order=(P, D, Q, 365)` on daily observations, annual seasonality is parameterized via a compact harmonic pair (`month_sin`, `month_cos`) alongside a binary Bay of Bengal South-West Monsoon indicator (`monsoon` for months `{6, 7, 8, 9}`).
- **Z-Score Regressor Standardization**: Exogenous features are standardized against the training window's mean and standard deviation (`exog_mean`, `exog_std` stored inside `ProjectionBundle`), reducing the exogenous design matrix condition number from `>1000` to `~20`.
- **L-BFGS with Nelder-Mead Simplex Warm Start (`_fit_with_warm_start`)**: If gradient optimization stalls on collinear freight regressors, `fit()` warm-starts from 800 Nelder-Mead simplex iterations before completing L-BFGS.
- **Zero-Refit Request Filtering (`_apply_to_latest`)**: During `POST /api/forecast`, the API calls `bundle.results.apply(frame["log_rate"], exog=exog, refit=False)`, running the state-space Kalman filter forward over the newest cached observations in milliseconds without re-estimating parameters.

### 2.3 The Circularity Guard (`OWN_DRIVER` vs. `CLASS_DRIVERS`)
Because vessel-class spot rates (`freight.rate.<class>`) are synthesized/calibrated from class-specific market proxies in `data/ingest.py`, feeding a vessel class its own generating proxy as an exogenous regressor would fit a trivial identity. `models/project.py` enforces `exog_features_for(vessel_class)` to drop the generating proxy for each class:
- `capesize` drops `log_gogl` (Golden Ocean equity)
- `panamax` drops `log_bdi` (Baltic Dry Index CFD proxy)
- `supramax` drops `log_sblk` (Star Bulk equity)
- `handysize` drops `log_sblk` (Star Bulk equity)

### 2.4 Berth-Level Physical & Tidal Resolution (`backend/data/ports/resolver.py`)
Ports do not have a single uniform draft—Paradip's iron ore berth and central quays differ by 5 meters, and Visakhapatnam's outer harbour (`~18m` for iron ore/coking coal) is structurally distinct from its inner harbour (`~14.5m` for thermal coal/fertilizers). `resolve_berth()` evaluates every individual berth in `berths.csv` and returns one of three commercially distinct verdicts:
- `ACCEPT_ALL_TIDE`: Vessel berths on arrival with `UKC_MARGIN_M = 0.4m` under-keel clearance and preferred comfort headroom (`0.5m`–`2.5m`).
- `ACCEPT_HIGH_TIDE_ONLY`: Vessel clears the berth only inside the tidal window (`draft_max_on_tide_m`), automatically adding `0.5` days of tidal waiting to `CallEconomics`.
- `REJECT`: Cannot berth as loaded. Constraints are evaluated in order of physical finality: **commodity handling** first, **LOA and beam** second, and **draft** last. If draft is the binding constraint at a shallow port (e.g., **Haldia**) and a lighterage anchorage exists in `lighterage_nodes.csv` (**Sandheads / Sagar**), the resolver computes a costed `LighteragePlan` using `TONNES_PER_CM` (`38` to `108` t/cm) with barge trips, mobilisation time (`0.75` days), added turnaround days, and USD cost.

### 2.5 Transparent Data Provenance & Graceful Degradation
- **Proxy Disclosure (`is_proxy`)**: Adapters that use public stand-ins for licensed feeds (such as TradingEconomics `BDIY:IND` CFD quotes or indicative Singapore VLSFO bunker levels) set `is_proxy = True`. This flag flows through `/api/data/status` and `/api/series` to the React UI's `DataOriginNotice` banner.
- **Dual-Layer Offline Resilience**:
  - If an external data source fails, `SourceAdapter.safe_fetch()` catches the exception, logs a warning, and serves the last cached series from `cache.db` marked `is_stale = True`.
  - If the FastAPI server itself is unreachable, `src/lib/api.ts` aborts after `8000ms` and `useApiResource` seamlessly switches to deterministic client-side fallbacks (`src/lib/fallbacks.ts`) while displaying an explicit status indicator in `ConnectionBadge`.

---

## 3. Technology Stack & Justifications

| Layer | Technology & Version | Architectural Justification |
| :--- | :--- | :--- |
| **Frontend UI** | React `19.2.8`, TypeScript `~6.0.2`, Vite `8.2.2`, React Router `7.18.3` | Strict type safety (`erasableSyntaxOnly`), sub-second HMR, and modular multi-page routing across 10 maritime workflows. |
| **Geospatial & Charts** | React-Leaflet `5.0.0` (`Leaflet 1.9.4`), Recharts `3.10.1`, Framer Motion `13.2.0` | Interactive East Coast port/anchorage mapping and confidence-band (`p80`/`p95`) rate trajectory plotting. |
| **Backend API** | FastAPI `>=0.115`, Uvicorn `>=0.30`, Pydantic `>=2.7` | High-throughput ASGI routing, automatic OpenAPI schema generation, and strict boundary validation. |
| **Econometrics & ML** | `statsmodels >=0.14,<0.15`, `scikit-learn` (GBR Quantiles), `pandas >=2.2`, `numpy >=1.26` | State-space SARIMAX with Kalman filtering (`apply(refit=False)`) plus quantile gradient boosting (`p10`/`p50`/`p90` `.joblib` models in `data/historical/models/`). |
| **Data Ingestion** | `APScheduler >=3.10`, `yfinance >=0.2.40`, `fredapi >=0.5.2`, `sqlite3` (WAL) | Zero-cost market/weather ingestion backed by an embedded concurrent SQLite WAL observation store. |
| **Verification & Linting** | `pytest >=8.0`, `hypothesis` (Property Testing), `oxlint 1.79.0` | Combines fast Rust-based frontend linting (`oxlint`) with mathematical invariant and property testing (`tests/` and `backend/tests/`). |

---

## 4. Repository Directory Layout

```text
SIH_Freight-Forecasting/
├── backend/                              # FastAPI service, SARIMAX engine & SQLite cache
│   ├── app/
│   │   ├── main.py                       # FastAPI lifespan, startup bootstrap, router registration
│   │   ├── config.py                     # Environment-driven configuration & paths
│   │   ├── costing.py                    # Spot vs CVC vs PTC voyage economics & multi-port split
│   │   ├── deps.py                       # AppState dependency injection & staleness helpers
│   │   ├── rates.py                      # Rate curve builder bridging forecasts to voyage departures
│   │   ├── reference.py                  # Discharge/loading port specs & vessel dimensions
│   │   ├── schemas.py                    # Pydantic v2 request/response contracts
│   │   └── routers/                      # Modular API routers (ports, match, forecast, contract, evaluate, series, status)
│   ├── data/
│   │   ├── cache.py                      # SQLite WAL store (observations & source_status tables)
│   │   ├── ingest.py                     # Bootstrap seeding & adapter orchestration
│   │   ├── snapshot.json                 # Committed ~200KB columnar baseline snapshot for offline boot
│   │   ├── adapters/                     # Failure-isolated adapters (baltic, equity, commodity, macro, fred, bunker, congestion, weather, ais)
│   │   ├── ports/
│   │   │   ├── berths.csv                # Berth-level dimensions, drafts, commodities & provenance URLs
│   │   │   ├── lighterage_nodes.csv      # Sandheads / Sagar anchorage barge parameters
│   │   │   ├── PROVENANCE.md             # Port authority source citations & caveats
│   │   │   ├── resolver.py               # Three-valued berth & lighterage resolution engine
│   │   │   └── schema.py                 # Berth & LighterageNode dataclasses and CSV loaders
│   │   └── reference/                    # Committed bunker_vlsfo.csv, congestion.json, corridors.json
│   ├── models/
│   │   ├── project.py                    # Log-SARIMAX fitting, Kalman filtering, drivers & backtesting
│   │   └── metrics.json                  # Committed rolling-origin backtest MAPE/RMSE scores
│   ├── scripts/
│   │   ├── refresh_snapshot.py           # Live pull -> SQLite cache -> columnar snapshot.json exporter
│   │   └── generate_baseline_snapshot.py # Standard-library synthetic-calibrated snapshot generator
│   ├── tests/                            # Backend pytest suite (test_berths, test_economics, test_ingestion, test_invariants)
│   ├── train.py                          # Offline CLI trainer producing models/sarimax_<class>.pkl
│   ├── requirements.txt                  # Runtime Python dependencies
│   └── requirements-dev.txt              # Test dependencies (pytest, httpx)
├── src/                                  # React 19 + TypeScript 6.0 Frontend Application
│   ├── components/                       # Layout (Header, Sidebar, ConnectionBadge) & common UI widgets
│   ├── context/                          # DataStatusProvider & live/stale/offline telemetry context
│   ├── data/                             # Static reference ports, vessels, cost assumptions & mock series
│   ├── hooks/                            # useApiResource hook with automatic fallback switching
│   ├── lib/                              # api.ts client, apiTypes.ts, cvcEngine.ts, evaluateApi.ts, fallbacks.ts, geo.ts
│   ├── pages/                            # 10 operational pages (CommandCenter, Map, Forecast, Matcher, ContractComparison, Evaluate, etc.)
│   └── store/                            # charterStore.tsx & themeStore.tsx state containers
├── data/                                 # Historical BDI CSVs, WPI dataset & parquet/joblib route models
├── tests/                                # Root property-based & unit tests (breakeven, monotonicity, ML quantiles)
├── docs/
│   ├── assets/
│   │   └── system-overview.svg           # System architecture diagram
│   ├── ARCHITECTURE.md                   # Detailed architecture specification
│   └── API.md                            # Complete REST API reference
├── run.sh                                # Unified process-group setup, training, test & launch script
├── package.json                          # Frontend dependencies & scripts
└── vite.config.ts                        # Vite 8 bundler configuration
```

---

## 5. End-to-End Data Flow Patterns

### 5.1 Multi-Voyage Spot vs. CVC vs. PTC Chartering Flow (`POST /api/contract`)
1. The user selects a load port (e.g., `newcastle`), discharge port (e.g., `paradip` or `haldia`), commodity (`thermal_coal`), vessel class (`Supramax`), parcel size (`55,000` tonnes), and programme length (`4` voyages) in `ContractComparison.tsx`.
2. `routers/contract.py` resolves the physical call via `costing.plan_call()`, invoking `resolver.resolve_berth()` against `berths.csv` and `lighterage_nodes.csv`. This determines the actual berth discharge rate (`tpd`), tidal waiting (`0.5d` if `ACCEPT_HIGH_TIDE_ONLY`), or barge lighterage cost and time penalty.
3. `costing.build_profile()` computes Haversine steaming distance (`haversine_nm * 1.18` routing factor), laden/ballast days, port turnaround, and total `round_trip_days`.
4. `rates.build_rate_curve()` projects the vessel class's SARIMAX rate trajectory (`mean` and `sd`) across the full programme horizon and samples departure dates spaced by `i * round_trip_days`.
5. `costing.evaluate()` prices every voyage under **Spot**, **CVC** (applying `cvc_discount_pct`, `CVC_BAF_HEDGE = 0.7`, and `CVC_WAIT_REDUCTION = 0.45`), and **Period Time Charter (`ptc`)** (using daily hire `TC_HIRE_USD_PER_DAY`, `2%` off-hire allowance, and `3.75%` address commission), returning total costs in `₹ Crore`, the exact `break_even_usd_per_t`, and the analytical `prob_spot_wins` using a correlated normal CDF (`RATE_ERROR_CORRELATION = 0.7`).
