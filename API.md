# FreightIQ REST API & Schema Reference

This document provides the complete technical reference for the **FreightIQ FastAPI Service** (`backend/app/main.py`, version `0.2.0`), including all endpoints, Pydantic v2 request/response schemas (`backend/app/schemas.py`), concrete JSON payloads, status codes, and client fallback contracts (`src/lib/api.ts`).

---

## 1. Base URL, CORS & Transport Semantics

- **Default Base URL**: `http://localhost:8000` (configured via `VITE_API_BASE` on the client and `FREIGHTIQ_API_PORT` in `./run.sh`)
- **Interactive OpenAPI Docs**:
  - Swagger UI: `http://localhost:8000/docs`
  - ReDoc: `http://localhost:8000/redoc`
  - OpenAPI JSON: `http://localhost:8000/openapi.json`
- **Authentication Scheme**: **None required** (open analytical service; CORS restricted via `FREIGHTIQ_CORS_ORIGINS`, defaulting to `http://localhost:5173,http://localhost:5174` for `GET`, `POST`, `OPTIONS`).
- **Client Timeout Contract (`src/lib/api.ts`)**: Browser `fetch` requests enforce an `8000ms` (`TIMEOUT_MS`) `AbortController` deadline. If the backend times out or returns a non-2xx status, `ApiError` is thrown and caught by `useApiResource`, which activates deterministic offline fallbacks (`src/lib/fallbacks.ts`).
- **Zero-Network Request Path**: All endpoints read exclusively from the local SQLite WAL cache (`backend/data/cache.db`), pre-loaded `ProjectionBundle` pickles, and committed berth CSVs.

---

## 2. Endpoint Summary Table

| Method | Path | Router (`backend/app/routers/`) | Tag | Description |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/health` | `main.py` | `meta` | Service liveness check and `offline_mode` status |
| `GET` | `/api/ports` | `ports.py` | `reference` | All discharge/loading ports, berths, lighterage nodes, vessel specs, and live congestion |
| `GET` | `/api/ports/{port_key}/berths` | `ports.py` | `reference` | Berth-level dimensions, drafts, commodities, and provenance URLs for one port |
| `GET` | `/api/ports/catalog` | `evaluate.py` | `evaluate` | Flat port catalog in the evaluator vocabulary (`PPA`, `VIZAG`, `HAY_POINT`, etc.) |
| `POST` | `/api/match` | `match.py` | `match` | Evaluates all 4 vessel classes against berth limits and lighterage nodes for a cargo parcel |
| `POST` | `/api/forecast` | `forecast.py` | `forecast` | Log-SARIMAX rate projection (`30`/`90`/`180`d), `p80`/`p95` bands, driver contributions, and what-if overrides |
| `POST` | `/api/contract` | `contract.py` | `contract` | Multi-voyage Spot vs. CVC vs. Period Time Charter (`ptc`) comparison in `₹ Crore` and `USD/t` |
| `POST` | `/api/contract/multiport` | `contract.py` | `contract` | Optimizes splitting a single parcel across two East Coast discharge ports |
| `POST` | `/api/evaluate` | `evaluate.py` | `evaluate` | Compatibility Spot vs. CVC evaluator with `p10`/`p50`/`p90` voyage breakdowns and lighterage plan |
| `GET` | `/api/series` | `series.py` | `series` | Raw cached time-series observations by metric list or namespace prefix |
| `GET` | `/api/series/metrics` | `series.py` | `series` | Lists all available metric names grouped by adapter namespace |
| `GET` | `/api/data/status` | `status.py` | `data` | Per-adapter freshness, staleness (`is_stale`), proxy flags (`is_proxy`), and startup validation notes |
| `POST` | `/api/data/refresh` | `status.py` | `data` | Triggers an immediate synchronous run of `ingest.refresh_all()` across all adapters |

---

## 3. Detailed Endpoint Specifications

### 3.1 `GET /api/health`
Returns service liveness and whether `FREIGHTIQ_OFFLINE` is active.

**Response `200 OK`:**
```json
{
  "status": "ok",
  "offline_mode": false
}
```

---

### 3.2 `GET /api/ports`
Returns all East Coast India discharge ports (`paradip`, `vizag`, `gangavaram`, `gopalpur`, `dhamra`, `sagar-sandheads`, `haldia`) with their constituent berths from `berths.csv`, lighterage anchorages from `lighterage_nodes.csv`, live congestion (`wait_days`, `vessels_at_anchor`), global loading ports, and vessel class specifications.

**Response `200 OK` (abbreviated):**
```json
{
  "as_of": "2026-10-28T16:50:00+00:00",
  "sources_stale": [],
  "provenance": {
    "berth_rows": 21,
    "lighterage_rows": 3
  },
  "commodities": ["coking_coal", "fertilizer", "general", "iron_ore", "limestone", "thermal_coal"],
  "discharge_ports": [
    {
      "id": "paradip",
      "name": "Paradip",
      "state": "Odisha",
      "lat": 20.2648,
      "lng": 86.6754,
      "berth_port_name": "Paradip",
      "is_anchorage": false,
      "deepest_berth_m": 16.5,
      "deepest_on_tide_m": 17.1,
      "live": {
        "wait_days": 2.4,
        "vessels_at_anchor": 7,
        "observed_at": "2026-10-28",
        "source": "reference:congestion.json"
      },
      "berths": [
        {
          "berth_id": "PAR-IOB",
          "port": "Paradip",
          "berth_name": "Iron Ore Berth (Mechanised)",
          "loa_max_m": 260.0,
          "beam_max_m": 43.0,
          "draft_max_m": 16.5,
          "draft_max_on_tide_m": 17.1,
          "commodities": ["iron_ore", "coking_coal"],
          "discharge_rate_tpd": 35000,
          "source_url": "https://paradipport.gov.in/",
          "source_date": "2025-11"
        }
      ],
      "lighterage_nodes": []
    }
  ],
  "loading_ports": [
    {
      "id": "newcastle",
      "name": "Newcastle",
      "country": "Australia",
      "lat": -32.9283,
      "lng": 151.7817
    }
  ],
  "vessel_specs": {
    "Handysize": {"dwt": 32000, "loa_m": 180.0, "beam_m": 28.0, "laden_draft_m": 10.2},
    "Supramax": {"dwt": 58000, "loa_m": 199.0, "beam_m": 32.3, "laden_draft_m": 12.8},
    "Panamax": {"dwt": 76000, "loa_m": 225.0, "beam_m": 32.3, "laden_draft_m": 14.2},
    "Capesize": {"dwt": 180000, "loa_m": 292.0, "beam_m": 45.0, "laden_draft_m": 18.2}
  }
}
```

---

### 3.3 `GET /api/ports/{port_key}/berths`
Returns all berths and lighterage nodes for a single port. Accepts either slug (`vizag`, `paradip`, `haldia`) or canonical name (`Visakhapatnam`, `Paradip`, `Haldia`).

**Example Request:** `GET /api/ports/haldia/berths`

**Response `200 OK`:**
```json
{
  "port": "Haldia",
  "berths": [
    {
      "berth_id": "HAL-4",
      "port": "Haldia",
      "berth_name": "Berth 4 (Coal / Bulk)",
      "loa_max_m": 230.0,
      "beam_max_m": 33.5,
      "draft_max_m": 8.2,
      "draft_max_on_tide_m": 9.1,
      "commodities": ["thermal_coal", "coking_coal", "limestone"],
      "discharge_rate_tpd": 12000,
      "source_url": "https://smportkolkata.shipping.gov.in/",
      "source_date": "2025-11"
    }
  ],
  "lighterage_nodes": [
    {
      "node_id": "SANDHEADS",
      "port": "Haldia",
      "node_name": "Sandheads Anchorage",
      "max_draft_m": 18.0,
      "barge_size_t": 2500,
      "transfer_rate_tpd": 8000,
      "cost_usd_per_t": 6.5
    }
  ],
  "provenance": {}
}
```

**Error Responses:**
- `404 Not Found`: `{"detail": "no berth or anchorage data for 'unknown_port'"}`

---

### 3.4 `POST /api/match`
Runs all four vessel classes (`Handysize`, `Supramax`, `Panamax`, `Capesize`) through `resolve_berth()` for a given discharge port, commodity, and parcel tonnage, ranking `ACCEPT_ALL_TIDE` ahead of `ACCEPT_HIGH_TIDE_ONLY` ahead of `REJECT`.

**Request Schema (`MatchRequest`):**
| Field | Type | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- |
| `discharge_port_id` | `str` | Required | Valid port slug or name | e.g., `"vizag"`, `"paradip"`, `"haldia"` |
| `cargo_tonnes` | `int` | Required | `> 0`, `<= 400000` | Parcel size in metric tonnes |
| `load_port_id` | `str \| null` | `null` | Optional | Load port slug |
| `commodity` | `str` | `"thermal_coal"` | Normalised commodity | `"thermal_coal"`, `"coking_coal"`, `"iron_ore"`, `"limestone"`, `"fertilizer"` |
| `vessel_draft_m` | `float \| null` | `null` | `> 0`, `<= 30` | Optional explicit draft override in meters |

**Concrete Request Payload:**
```json
{
  "discharge_port_id": "haldia",
  "cargo_tonnes": 52000,
  "commodity": "thermal_coal"
}
```

**Response `200 OK` (`MatchResponse`):**
```json
{
  "discharge_port_id": "haldia",
  "discharge_port_name": "Haldia",
  "commodity": "thermal_coal",
  "cargo_tonnes": 52000,
  "as_of": "2026-10-28T16:50:00+00:00",
  "sources_stale": [],
  "provenance": {},
  "recommendations": [
    {
      "vessel_class": "Supramax",
      "outcome": "REJECT",
      "reason": "Draft 12.15m + 0.40m UKC exceeds Haldia Berth 4 tidal limit 9.10m; lighterage available via Sandheads",
      "laden_draft_m": 12.15,
      "berth": null,
      "turnaround_days": 8.42,
      "estimated_rate_usd_per_t": 15.84,
      "lighterage": {
        "node_id": "SANDHEADS",
        "node_name": "Sandheads Anchorage",
        "tonnes_to_lighten": 17940.0,
        "barge_trips": 8,
        "added_days": 2.99,
        "cost_usd": 116610.0,
        "resulting_draft_m": 8.7,
        "onward_berth_id": "HAL-4",
        "onward_outcome": "ACCEPT_HIGH_TIDE_ONLY",
        "narrative": "Lighten 17,940t at Sandheads (8 barge trips, +3.0d, $116.6k) to reach 8.70m for Haldia Berth 4 on high water.",
        "provenance": {
          "source_url": "https://smportkolkata.shipping.gov.in/",
          "source_date": "2025-11"
        }
      },
      "considered": []
    }
  ]
}
```

**Error Responses:**
- `404 Not Found`: Unknown `discharge_port_id`.
- `422 Unprocessable Entity`: `cargo_tonnes` outside `(0, 400000]`.

---

### 3.5 `POST /api/forecast`
Projects daily per-tonne freight rates (`USD/tonne`) for a vessel class using the pre-trained log-SARIMAX model (`SARIMAXResults.apply(..., refit=False)`) with asymmetric `p80` and `p95` confidence bands, dollar-per-tonne exogenous driver contributions, rolling backtest accuracy metrics, and optional what-if scenario overrides.

**Request Schema (`ForecastRequest`):**
| Field | Type | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- |
| `vessel_class` | `Literal` | `"Supramax"` | `"Handysize" \| "Supramax" \| "Panamax" \| "Capesize"` | Target dry-bulk vessel class |
| `horizon_days` | `Literal` | `90` | `30 \| 90 \| 180` | Forecast horizon in days |
| `history_days` | `int` | `180` | `30 <= history_days <= 1095` | Number of historical days returned |
| `scenario` | `dict[str, float] \| null` | `null` | Keys: `bdi`, `bunker`, `coal`, `iron_ore`, `usdinr`, `monsoon` | Optional what-if overrides in natural units (e.g., `{"bunker": 800}`) |

**Concrete Request Payload:**
```json
{
  "vessel_class": "Panamax",
  "horizon_days": 90,
  "history_days": 180,
  "scenario": {
    "bunker": 720.0,
    "coal": 135.0
  }
}
```

**Response `200 OK` (`ForecastResponse`):**
```json
{
  "vessel_class": "Panamax",
  "unit": "USD/tonne",
  "history": [
    {"date": "2026-05-01", "value": 14.21},
    {"date": "2026-05-02", "value": 14.35}
  ],
  "forecast": [
    {"date": "2026-10-29", "value": 14.88},
    {"date": "2026-10-30", "value": 14.92}
  ],
  "intervals": {
    "p80": [
      {"date": "2026-10-29", "lower": 13.95, "upper": 15.87}
    ],
    "p95": [
      {"date": "2026-10-29", "lower": 13.48, "upper": 16.42}
    ]
  },
  "drivers": [
    {
      "feature": "Bunker price (VLSFO Singapore)",
      "key": "log_bunker",
      "coefficient": 0.1421,
      "contribution": 0.642
    },
    {
      "feature": "Annual seasonality",
      "key": "seasonality",
      "coefficient": null,
      "contribution": -0.215
    }
  ],
  "accuracy": {
    "mape": 6.842,
    "rmse": 1.124,
    "folds": 4,
    "horizon_days": 90,
    "backtest": "rolling-origin-4fold"
  },
  "as_of": "2026-10-28T16:50:00+00:00",
  "sources_stale": [],
  "model": "sarimax",
  "notes": [
    "What-if applied: {'bunker': 720.0, 'coal': 135.0}",
    "log_bdi excluded from this class's regressors: it derives the target"
  ]
}
```

**Error & Fallback Behavior:**
- If no pickle exists for `vessel_class`, returns `200 OK` with `"model": "naive-fallback"` (random-walk band widening with $\sqrt{t}$) and an explanatory note in `notes`.
- `503 Service Unavailable`: If `cache.db` has zero observations for the requested class.

---

### 3.6 `POST /api/contract`
Prices a multi-voyage bulk cargo import programme across **Spot**, **Consecutive Voyage Charter (CVC)**, and **Period Time Charter (`ptc`)**, spacing voyage departures by the resolved berth and lighterage turnaround time.

**Request Schema (`ContractRequest`):**
```json
{
  "load_port_id": "newcastle",
  "discharge_port_id": "paradip",
  "commodity": "thermal_coal",
  "vessel_class": "Supramax",
  "cargo_tonnes": 55000,
  "num_voyages": 4,
  "bunker_price_usd": 620.0,
  "demurrage_usd_per_day": 22000.0,
  "cvc_discount_pct": 5.0
}
```

**Response `200 OK` (`ContractResponse`):**
```json
{
  "route": "Newcastle -> Paradip",
  "vessel_class": "Supramax",
  "num_voyages": 4,
  "spot_total_cr": 36.42,
  "cvc_total_cr": 34.18,
  "delta_cr": 2.24,
  "break_even_usd_per_t": 15.12,
  "prob_spot_wins": 0.284,
  "locked_rate_usd_per_t": 15.05,
  "market_rate_usd_per_t": 15.84,
  "forecast_avg_usd_per_t": 16.21,
  "line_items": [
    {"label": "Base Ocean Freight", "spot_cr": 31.54, "cvc_cr": 29.30, "note": "5.0% CVC volume discount"},
    {"label": "Bunker Adjustment (BAF)", "spot_cr": 0.84, "cvc_cr": 0.59, "note": "70% BAF hedge under CVC"},
    {"label": "Port & Berth Dues", "spot_cr": 2.41, "cvc_cr": 2.41, "note": null},
    {"label": "Pre-Berthing Demurrage", "spot_cr": 1.63, "cvc_cr": 1.88, "note": "45% queue reduction under CVC stem"}
  ],
  "lighterage_tonnes": 0.0,
  "blocked_reason": null,
  "berth": {
    "berth_id": "PAR-CQ1",
    "berth_name": "Central Quay 1",
    "outcome": "ACCEPT_ALL_TIDE"
  },
  "ptc": {
    "total_cr": 35.10,
    "daily_hire_usd": 14200.0,
    "charter_days": 114.2
  },
  "cheapest_structure": "cvc",
  "voyages": [],
  "headline": "CVC saves ₹2.24 Cr across 4 voyages (break-even spot rate: $15.12/t)",
  "as_of": "2026-10-28T16:50:00+00:00",
  "sources_stale": []
}
```

---

### 3.7 `POST /api/contract/multiport`
Evaluates splitting a single parcel across two discharge ports (e.g., discharging part cargo at deep-water **Gangavaram** so the lightened vessel can enter shallow-draft **Haldia** without barge lighterage).

**Request Payload (`MultiPortRequest`):**
```json
{
  "load_port_id": "newcastle",
  "discharge_port_ids": ["gangavaram", "haldia"],
  "vessel_class": "Panamax",
  "commodity": "thermal_coal",
  "total_tonnes": 72000,
  "demurrage_usd_per_day": 22000.0
}
```

**Response `200 OK`:** Returns single-port vs. two-port split cost breakdowns, optimal split tonnage at port 1 vs. port 2, resulting arrival draft at port 2, and net savings in USD and `₹ Crore`.

---

### 3.8 `GET /api/ports/catalog` & `POST /api/evaluate`
Compatibility endpoints backing the `Evaluate.tsx` page using uppercase port/vessel codes (`PPA`, `VIZAG`, `GANGAVARAM`, `GOPALPUR`, `DHAMRA`, `HALDIA`, `HAY_POINT`, `NEWCASTLE`, `TABONEO`, `MAPUTO`, `BALTIMORE` and `HANDYSIZE`, `SUPRAMAX`, `PANAMAX`, `CAPESIZE`).

**`POST /api/evaluate` Request Payload (`EvaluateRequest`):**
```json
{
  "cargo_tonnage": 75000,
  "origin_code": "NEWCASTLE",
  "destination_code": "PPA",
  "vessel_code": "PANAMAX",
  "num_voyages": 4,
  "cvc_discount_pct": 5.0
}
```

**Response `200 OK`:** Returns `is_cvc_favorable`, `locked_cvc_rate`, `average_spot_rate`, `spot_total_usd`, `cvc_total_usd`, `base_case_delta_usd`, `base_case_delta_inr`, `base_case_delta_cr`, `breakeven_spot_rate`, `breakeven_probability_pct`, `p10_rates`, `p50_rates`, `p90_rates`, per-voyage breakdown (`voyages`), and `lighterage_plan`.

---

### 3.9 `GET /api/series` & `GET /api/series/metrics`
Query raw cached time-series observations from `cache.db`.

**Query Parameters for `GET /api/series`:**
- `metrics` (`str`, optional): Comma-separated metric names (max `40`), e.g. `baltic.bdi,bunker.vlsfo.singapore`.
- `prefix` (`str`, optional): Metric namespace prefix, e.g. `congestion` or `freight.rate`.
- `days` (`int`, default `365`, range `1`–`1825`): Lookback window in days.
- `latest_only` (`bool`, default `false`): Return only the most recent observation per metric.

**Example Request:** `GET /api/series?metrics=baltic.bdi,macro.usdinr&days=30&latest_only=true`

**Response `200 OK`:**
```json
{
  "as_of": "2026-10-28T16:50:00+00:00",
  "sources_stale": [],
  "requested": ["baltic.bdi", "macro.usdinr"],
  "missing": [],
  "series": {
    "baltic.bdi": {
      "source": "tradingeconomics:BDIY:IND",
      "adapter": "baltic",
      "is_proxy": true,
      "points": [{"date": "2026-10-28", "value": 1582.0}]
    },
    "macro.usdinr": {
      "source": "fred:DEXINUS",
      "adapter": "macro",
      "is_proxy": false,
      "points": [{"date": "2026-10-28", "value": 88.4}]
    }
  }
}
```

---

### 3.10 `GET /api/data/status` & `POST /api/data/refresh`
Inspects per-adapter freshness, proxy status, and startup validation warnings, or triggers an on-demand ingestion cycle.

**`GET /api/data/status` Response `200 OK` (`DataStatusResponse`):**
```json
{
  "as_of": "2026-10-28T16:50:00+00:00",
  "offline_mode": false,
  "stale_after_minutes": 180,
  "snapshot_provenance": "synthetic-calibrated",
  "sources": [
    {
      "source": "baltic",
      "last_fetched": "2026-10-28T16:00:00+00:00",
      "last_success": "2026-10-28T16:00:00+00:00",
      "is_stale": true,
      "age_minutes": 50.0,
      "row_count": 1095,
      "error": null,
      "is_proxy": true,
      "source_label": "TradingEconomics BDIY:IND (CFD proxy)",
      "notes": []
    }
  ]
}
```
