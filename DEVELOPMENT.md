# FreightIQ Developer Environment & Engineering Guide

This guide covers local development workflows, virtual environment setup, SQLite WAL cache migrations, snapshot seeding/refresh scripts, model training (`train.py`), and testing suites for **FreightIQ** (`SIH_Freight-Forecasting`).

---

## 1. Local Developer Environment Setup

### 1.1 Toolchain & Runtime Versions
- **Python**: **CPython `3.11`, `3.12`, or `3.13`** (Recommended: `3.12`).
  > **Important**: Avoid Python `3.14+` for the backend virtualenv (`backend/.venv`) because `statsmodels` and `pandas` binary wheels may not be published yet and will attempt a slow source compilation. `./run.sh` automatically guards against Python `3.14` and selects `python3.12` (or provisions it via `uv venv --python 3.12`).
- **Node.js**: `v18.0+` or `v20+` with `npm`.
- **Frontend Compiler & Linter**: TypeScript `~6.0.2` (`tsc -b`), Vite `^8.2.2`, and `oxlint ^1.79.0`.

### 1.2 Environment Configuration (`.env`)
Copy `.env.example` to `.env` in the repository root:
```bash
cp .env.example .env
```
Default contents:
```ini
VITE_API_BASE=http://localhost:8000
```
If `VITE_API_BASE` is omitted or the backend is stopped, the React application automatically falls back to bundled reference data (`src/lib/fallbacks.ts`) after an 8-second timeout (`src/lib/api.ts`) and displays an offline indicator in `ConnectionBadge`.

### 1.3 Setting Up the Python Backend (`backend/`)
```bash
cd backend
python3.12 -m venv .venv

# Activate virtual environment
# Linux / macOS:
source .venv/bin/activate
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# Install runtime + test dependencies (FastAPI, statsmodels, pandas, pytest, httpx)
pip install -r requirements-dev.txt
```

### 1.4 Setting Up the React Frontend
```bash
npm install
npm run dev
```

---

## 2. Database Schema, Snapshot Seeding & Offline Cache

### 2.1 SQLite WAL Cache (`backend/data/cache.py`)
FreightIQ stores all time-series observations and adapter health telemetry in `backend/data/cache.db` using SQLite Write-Ahead Logging (`PRAGMA journal_mode=WAL`):

```sql
CREATE TABLE IF NOT EXISTS observations (
    metric     TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    value      REAL NOT NULL,
    source     TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (metric, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_observations_metric ON observations (metric, timestamp);

CREATE TABLE IF NOT EXISTS source_status (
    source       TEXT PRIMARY KEY,
    last_fetched TEXT,
    last_success TEXT,
    is_stale     INTEGER NOT NULL DEFAULT 1,
    error        TEXT,
    row_count    INTEGER NOT NULL DEFAULT 0,
    is_proxy     INTEGER NOT NULL DEFAULT 0,
    source_label TEXT,
    notes        TEXT
);
```

### 2.2 Automatic Schema Migration (`_migrate`)
On connection initialization (`cache.connect()`), `_migrate(conn)` inspects `PRAGMA table_info(source_status)` and idempotently applies `ALTER TABLE source_status ADD COLUMN` for late-added columns (`is_proxy`, `source_label`, `notes`).

### 2.3 Cold-Boot Snapshot Seeding & Refresh Scripts
1. **Automatic Cold-Boot Seed (`ingest.bootstrap`)**:
   When FastAPI starts, if `observations` in `cache.db` is empty, `ingest.bootstrap(conn)` loads `backend/data/snapshot.json` (`~200 KB` columnar JSON) into SQLite so every endpoint works immediately without network access.
2. **Refreshing the Snapshot from Live Feeds (`backend/scripts/refresh_snapshot.py`)**:
   ```bash
   cd backend
   python scripts/refresh_snapshot.py              # Pull all live adapters -> cache.db -> snapshot.json
   python scripts/refresh_snapshot.py --days 730   # Export 2 years of history
   python scripts/refresh_snapshot.py --skip-fetch # Export existing cache.db without network fetch
   python scripts/refresh_snapshot.py --allow-stale# Allow export even if a source is rate-limited
   ```
3. **Generating a Calibrated Synthetic Baseline (`backend/scripts/generate_baseline_snapshot.py`)**:
   If developing in an air-gapped environment with zero market access, regenerate `snapshot.json` using only the Python standard library:
   ```bash
   cd backend
   python scripts/generate_baseline_snapshot.py --days 1095
   ```
   This stamps `provenance: "synthetic-calibrated"` so the UI explicitly labels the data as synthetic.

### 2.4 Berth & Lighterage Reference Fixtures (`backend/data/ports/`)
- `backend/data/ports/berths.csv`: Berth-by-berth maximum draft (`draft_max_m`), tidal draft (`draft_max_on_tide_m`), LOA (`loa_max_m`), beam (`beam_max_m`), handled commodities, discharge rate (`discharge_rate_tpd`), and `source_url` / `source_date`.
- `backend/data/ports/lighterage_nodes.csv`: Anchorage lighterage parameters (Sandheads, Sagar) for deep-draft vessels calling at riverine ports like Haldia.

---

## 3. Training the Forecasting Models (`backend/train.py`)

Model estimation (`SARIMAX(1, 1, 1)` with exogenous regressors and 4-fold rolling-origin backtesting) is strictly separated from the HTTP request path:

```bash
cd backend

# Fit all 4 vessel classes (handysize, supramax, panamax, capesize) + run 4-fold backtest
python train.py

# Fit a single vessel class
python train.py --classes capesize

# Pull live market data before fitting
python train.py --refresh

# Skip rolling-origin backtest for fast iteration during development
python train.py --no-backtest
```
Outputs written by `train.py`:
- `backend/models/sarimax_handysize.pkl`
- `backend/models/sarimax_supramax.pkl`
- `backend/models/sarimax_panamax.pkl`
- `backend/models/sarimax_capesize.pkl`
- `backend/models/metrics.json` (committed accuracy scores read by `/api/forecast`)

---

## 4. Testing, Property Verification & Linting

### 4.1 Backend Pytest Suite (`backend/tests/`)
Tests berth resolution outcomes (`ACCEPT_ALL_TIDE`, `ACCEPT_HIGH_TIDE_ONLY`, `REJECT`), lighterage calculations, voyage economics, adapter fault isolation, and circularity invariants:
```bash
cd backend
pytest tests -v
```
- `backend/tests/test_berths.py`: Verifies Vizag inner/outer basin separation, Haldia lighterage via Sandheads/Sagar, and binding constraint ordering (commodity -> LOA/beam -> draft).
- `backend/tests/test_economics.py`: Verifies Spot vs. CVC vs. Period Time Charter (`ptc`) costing, break-even rate solver, and multi-port cargo splits.
- `backend/tests/test_ingestion.py`: Verifies `SourceAdapter.safe_fetch()` fallback, SQLite WAL caching, and offline mode (`FREIGHTIQ_OFFLINE=1`).
- `backend/tests/test_invariants.py`: Verifies `OWN_DRIVER` and `CLASS_DRIVERS` consistency and monotonic economics invariants.

### 4.2 Root Quantitative & Property-Based Tests (`tests/`)
Uses `pytest` and `hypothesis` (`@given`) to test mathematical invariants across the ML quantile pipeline (`p10 <= p50 <= p90`), break-even monotonicity, and CVC discount monotonicity:
```bash
pytest tests -v
```
- `tests/test_breakeven_analyzer.py` & `tests/test_breakeven_invariant.py`
- `tests/test_discount_monotonicity.py`
- `tests/test_ml_pipeline.py` & `tests/test_ml_quantiles.py`
- `tests/test_voyage_costs.py` & `tests/test_engine.py`

### 4.3 Frontend Type-Checking, Linting & Production Build
```bash
# Run Oxlint static analysis (configured in .oxlintrc.json)
npm run lint

# Run TypeScript 6.0 project references check and Vite 8 production build
npm run build

# Run both backend and frontend test/lint suites in one command
./run.sh --test
```
