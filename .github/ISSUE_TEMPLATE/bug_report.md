---
name: Bug Report
about: Report a bug in SARIMAX forecasting, berth resolution, Spot vs CVC costing, data ingestion, or the React UI
title: "[BUG] "
labels: ["bug"]
assignees: ""
---

## Bug Summary
A clear and concise description of the issue and which FreightIQ subsystem is affected (`SARIMAX /api/forecast`, `Berth Resolver /api/match`, `Costing /api/contract`, `Adapter Ingestion /api/data/status`, or `React Dashboard`).

## Steps to Reproduce
1. Start the stack (`./run.sh` or `uvicorn` + `vite`)
2. Send request to endpoint `'...'` or open page `'...'` (e.g., `/forecast`, `/matcher`, `/contracts`, `/evaluate`)
3. Input parameters `'...'` (e.g., `vessel_class="Panamax"`, `discharge_port_id="haldia"`, `cargo_tonnes=72000`)
4. Observe unexpected output or error.

## Expected Behavior
Describe the expected forecast, berth outcome (`ACCEPT_ALL_TIDE`, `ACCEPT_HIGH_TIDE_ONLY`, `REJECT`), cost calculation, or UI state.

## Actual Behavior
Describe what actually occurred, including exact JSON responses or browser console / Uvicorn logs.

## Logs / Payloads / Screenshots
```json
Paste relevant request/response JSON payloads or stack traces from .run-logs/api.log here.
```

## Environment Information
- **OS**: (e.g., Windows 11 / Ubuntu 24.04 / macOS)
- **Python Version**: (e.g., CPython 3.12.6)
- **Node.js Version**: (e.g., v20.14.0)
- **Mode**: (Online / `FREIGHTIQ_OFFLINE=1` / Static Frontend Fallback)
