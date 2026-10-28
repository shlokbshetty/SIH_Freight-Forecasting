# FreightIQ Support & Troubleshooting Guide

Need assistance setting up, training models, or troubleshooting **FreightIQ** (`SIH_Freight-Forecasting`)? This guide lists support channels, issue labels, and answers to common engineering questions.

---

## 1. Support Channels

| Channel | Best For | Reference |
| :--- | :--- | :--- |
| **GitHub Issues** | Reproducible bugs, berth data updates, and feature proposals | `.github/ISSUE_TEMPLATE/bug_report.md` / `feature_request.md` |
| **Architecture & API Docs** | SARIMAX model specification, berth resolver logic, and REST schemas | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) & [docs/API.md](docs/API.md) |
| **Port Provenance Docs** | Verifying port authority sources for East Coast India berths | [backend/data/ports/PROVENANCE.md](backend/data/ports/PROVENANCE.md) |
| **Developer Guide** | Local setup, snapshot scripts, and pytest / Hypothesis commands | [DEVELOPMENT.md](DEVELOPMENT.md) |

---

## 2. Issue Tracker Labels

- `bug`: Incorrect calculation, API error, or UI rendering defect.
- `enhancement`: New analytical feature, chart, or chartering structure.
- `domain:sarimax-forecast`: `backend/models/project.py`, `train.py`, or `/api/forecast` issues.
- `domain:berth-resolver`: `backend/data/ports/resolver.py`, `berths.csv`, `lighterage_nodes.csv`, or `/api/match` issues.
- `domain:costing-cvc`: `backend/app/costing.py`, `/api/contract`, `/api/evaluate`, or `src/lib/cvcEngine.ts` issues.
- `domain:ingestion-cache`: `backend/data/adapters/`, `cache.py`, `snapshot.json`, or `/api/data/status` issues.
- `domain:frontend-ui`: React 19 pages (`src/pages/`), `useApiResource`, or Leaflet/Recharts components.

---

## 3. Project-Specific FAQs

### Q1: Why does `pip install -r requirements.txt` fail or hang while building `statsmodels` or `pandas`?
**Answer**: You are likely running Python `3.14`, which does not yet have pre-built manylinux/Windows wheels for `statsmodels >=0.14,<0.15` and attempts to compile C/Fortran extensions from source. Use **CPython `3.11`, `3.12`, or `3.13`** (or install `uv`, which `./run.sh` automatically uses to download CPython `3.12`).

### Q2: Why does `/api/data/status` report `"is_stale": true` for adapters on a fresh clone?
**Answer**: By design, `backend/data/snapshot.json` seeds `cache.db` on startup without making network calls (`FREIGHTIQ_REFRESH_ON_STARTUP` defaults to `False`). Seeded observations carry the timestamp of the snapshot and are honestly flagged as `is_stale: true` until the hourly scheduler runs or you trigger `POST /api/data/refresh` (or run `python scripts/refresh_snapshot.py`).

### Q3: Why does `/api/forecast` return `"model": "naive-fallback"`?
**Answer**: Model pickles (`backend/models/sarimax_<class>.pkl`) are git-ignored so binary blobs are not committed to git. Run `cd backend && python train.py` (or `./run.sh --retrain`) to fit the SARIMAX pickles from `cache.db`. Once generated, restart the FastAPI server and `/api/forecast` will return `"model": "sarimax"`.

### Q4: How do I prove the application works 100% offline?
**Answer**: Run `./run.sh --offline` or start the backend with `FREIGHTIQ_OFFLINE=1 uvicorn app.main:app --port 8000`. All outbound adapter calls are blocked at the transport boundary, and every API endpoint and React screen continues to operate from `cache.db` and `snapshot.json`.

### Q5: How do I stop background processes if ports `8000` or `5173` remain bound?
**Answer**: Run `./run.sh --stop` to cleanly terminate any processes listening on `FREIGHTIQ_API_PORT` (`8000`) and `FREIGHTIQ_WEB_PORT` (`5173`).
