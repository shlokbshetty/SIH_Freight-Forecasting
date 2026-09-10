# PORTS AND ML SPEC
## Intelligent Freight Procurement & Vessel Feasibility Decision Support Platform
### Ministry of Ports, Shipping and Waterways (MoPSW) — Sagarmanthan Decision Support System

---

> **Branch:** `feat/port-vessel-feasibility-cli`  
> **Stack:** Python 3.10+ · LightGBM · scikit-learn · Pandas · PyArrow · Rich  
> **Interface:** Terminal CLI (`cli.py`) with `rich` formatted tables + `matplotlib` diagnostic reports

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Section A — Physical Port Architecture & Vessel Feasibility Engine](#section-a--physical-port-architecture--vessel-feasibility-engine)
3. [Section B — ML Freight Forecasting Architecture](#section-b--ml-freight-forecasting-architecture)
4. [Section C — Financial Evaluation Engine](#section-c--financial-evaluation-engine)
5. [Section D — Model Evaluation & Visualization](#section-d--model-evaluation--visualization)
6. [Section E — CLI Interface Reference](#section-e--cli-interface-reference)
7. [Section F — Project Structure](#section-f--project-structure)

---

## 1. System Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│           SAGARMANTHAN FREIGHT PROCUREMENT CLI (cli.py)              │
│                                                                      │
│   --demo         Two-scenario Ministry presentation                  │
│   --cargo        Custom cargo evaluation                             │
│   --update-data  Live market data sync (Yahoo Finance)               │
│   --train-ml     Retrain LightGBM quantile models                    │
│   --evaluate     Diagnostic metrics + reports/plots/ artefacts       │
└───────────────────┬──────────────────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
┌───────────────┐     ┌──────────────────────┐
│  FEASIBILITY  │     │   FINANCIAL EVALUATOR │
│   ENGINE      │     │   financial_evaluat-  │
│ feasibility.py│     │   or.py               │
└───────┬───────┘     └──────────┬───────────┘
        │                        │
        ▼                        ▼
┌───────────────┐     ┌──────────────────────┐
│  Port/Vessel  │     │  ML FORECASTER        │
│  Registries   │     │  ml_forecaster.py     │
│  ports.py     │     │  (Multi-Quantile      │
│  vessels.py   │     │   LightGBM p10/50/90) │
└───────────────┘     └──────────┬───────────┘
                                 │
                      ┌──────────┴───────────┐
                      ▼                      ▼
             ┌────────────────┐   ┌──────────────────┐
             │  DATA FETCHER  │   │ FEATURE ENGINEER  │
             │  fetcher.py    │   │ features.py       │
             │  (Parquet cache│   │ (lags, rolling    │
             │  + yfinance)   │   │  stats, seasonal) │
             └────────────────┘   └──────────────────┘
```

---

## Section A — Physical Port Architecture & Vessel Feasibility Engine

### A1. East Coast Indian Port Registry (`data/ports.py`)

The platform models **7 primary East Coast Indian ports** acting as bulk import/export hubs, plus **5 international origin ports** for global trade corridors.

#### Indian Port Parameters

| Port | Code | Max Draft (m) | Max LOA (m) | Max Beam (m) | Load/Disch Rate (TPD) | Notes |
|------|------|:---:|:---:|:---:|:---:|---|
| Paradip | PPA | 17.0 | 280.0 | 45.0 | 45,000 | Deepwater NCTPS coal berth |
| Dhamra | DHM | 18.5 | 300.0 | 50.0 | 50,000 | Deep channel, Adani terminal |
| Haldia | HLD | 8.5 | 200.0 | 32.0 | 25,000 | River silting; Sagar STS triggered |
| Gangavaram | GNV | 21.0 | unlimited | unlimited | 60,000 | Unconstrained deepwater |
| Vizag (VSPL) | VZG | 16.5 | 275.0 | 45.0 | 55,000 | NMDC ore terminal |
| Kamarajar | KPT | 17.5 | 290.0 | 46.0 | 50,000 | Ennore coal + iron ore |
| Chennai | CHN | 14.0 | 265.0 | 42.0 | 40,000 | Versatile; draft limited |

#### International Load Port Parameters

| Port | Code | Country | Max Draft (m) | Commodity |
|------|------|---------|:---:|---|
| Newcastle | NCL | Australia | unlimited | Thermal Coal |
| Hay Point | HAP | Australia | unlimited | Metallurgical Coal |
| Taboneo | TBN | Indonesia | unlimited | Thermal Coal |
| Maputo | MPT | Mozambique | unlimited | Metallurgical Coal |
| Baltimore | BWI | USA | unlimited | Metallurgical Coal |

> **Design Note:** International load ports are treated as unconstrained. All dimensional feasibility constraints are evaluated at the **Indian discharge port**.

---

### A2. Vessel Class Dimensional Registry (`data/vessels.py`)

Five bulk dry vessel archetypes are registered. Operating draft at partial load is computed using linear interpolation between light-ship and design-draft.

| Vessel Class | Code | DWT Range (MT) | Design Draft (m) | LOA (m) | Beam (m) | Typical Route |
|---|---|:---:|:---:|:---:|:---:|---|
| Handysize | HANDYSIZE | 15,000–35,000 | 10.2 | 170 | 27 | All Indian ports |
| Supramax | SUPRAMAX | 45,000–60,000 | 13.0 | 200 | 32 | Paradip, Gangavaram |
| Panamax | PANAMAX | 60,000–80,000 | 14.0 | 225 | 32.3 | Dhamra, Paradip |
| Kamsarmax | KAMSARMAX | 80,000–87,000 | 14.2 | 229 | 32.3 | Dhamra |
| Capesize | CAPESIZE | 130,000–200,000 | 18.5 | 295 | 48 | Gangavaram, Dhamra |

**Draft at Tonnage Formula:**

```
draft_operating = draft_light + (cargo_tonnage / dwt_max) x (draft_design - draft_light)
```

---

### A3. Feasibility Engine Logic (`engine/feasibility.py`)

The `FeasibilityEngine.evaluate_route()` method screens all registered vessel classes against a given cargo and port pair.

**Evaluation Sequence:**

1. **Cargo Size Gate**: Reject vessel if `dwt_max < cargo_tonnage`.
2. **Origin Port Check**: Validate draft, LOA, beam against origin constraints.
3. **Destination Port Check**: Validate discharge port dimensional constraints at operating draft.
4. **Lighterage Trigger**: If `destination.max_draft < vessel_operating_draft` → flag for Sagar/Sandheads STS.
5. **Suitability Scoring**: Composite score (0–100) based on clearance margins and operational efficiency.

**Clearance Margin:**
```
clearance = port_max_draft - vessel_operating_draft
```
- Positive → passes
- Negative at destination → lighterage evaluated; negative at origin → REJECTED

---

### A4. Sagar / Sandheads Lighterage Router (`engine/feasibility.py` → `LighteragePlan`)

Haldia Port's maximum permissible dock draft is **8.5 m**. Any vessel with operating draft exceeding 8.5 m is routed via the Sagar/Sandheads deepwater anchorage for ship-to-ship (STS) transfer.

**Lighterage Calculation:**

```
excess_draft      = vessel_operating_draft - destination.max_draft
lightered_fraction = excess_draft / vessel_operating_draft
lightered_tonnage  = lightered_fraction x cargo_tonnage
retained_tonnage   = cargo_tonnage - lightered_tonnage

lighterage_cost    = lightered_tonnage x 3.50  (USD/T)
time_penalty_days  = 1.5 days
```

| Parameter | Value |
|---|:---:|
| Sagar Anchorage Depth | 15.0 m |
| Lighterage Tariff | $3.50 / MT |
| STS Time Penalty | +1.5 days |

---

## Section B — ML Freight Forecasting Architecture

### B1. Data Ingestion & Parquet Storage (`data/fetcher.py`)

The platform uses an **offline-first Parquet cache** backed by `pyarrow`.

#### Directory Structure

```
data/historical/
├── macro_data.parquet        # 1,220+ daily macro proxy records
├── route_fixtures.parquet    # Monthly freight rates (37 records, 5 corridors)
└── models/
    ├── NEWCASTLE_HALDIA_PANAMAX_p10.joblib
    ├── NEWCASTLE_HALDIA_PANAMAX_p50.joblib
    ├── NEWCASTLE_HALDIA_PANAMAX_p90.joblib
    └── ... (3 models x 5 routes = 15 .joblib files total)
```

#### Macro Proxy Variables

| Variable | Ticker / Source | Description |
|---|---|---|
| `GOGL` | Oslo GOGL | Golden Ocean dry bulk shipping proxy |
| `SBLK` | NYSE SBLK | Star Bulk Carriers shipping proxy |
| `ZIM` | NYSE ZIM | Container rate proxy |
| `COAL_NEWCASTLE` | MTF=F (Yahoo) | Newcastle thermal coal front-month |
| `IRON_ORE` | SCOI (Yahoo) | Iron ore spot proxy |
| `BRENT_CRUDE` | BZ=F (Yahoo) | Brent crude (bunker fuel proxy) |
| `USD_INR` | INR=X (Yahoo) | USD/INR exchange rate |
| `USD_AUD` | AUDUSD=X (Yahoo) | USD/AUD (Australia cargo origin) |

#### Update Policy

- **`python cli.py --update-data`**: Polls Yahoo Finance via `yfinance`, downloads 5 years of daily OHLC, and upserts local Parquet files.
- **Regular execution**: Reads directly from local Parquet — **no network calls**.

---

### B2. Feature Engineering Pipeline (`data/features.py`)

| Group | Features | Count |
|---|---|:---:|
| Base Values | Raw daily close for all 8 macro columns | 8 |
| Lag Features | t-1, t-7, t-14, t-30 for each macro variable | 32 |
| Rolling MA | 7-day and 30-day moving average | 16 |
| Rolling Std | 7-day and 30-day rolling standard deviation | 16 |
| Domain Ratios | `coal_to_bunker_ratio`, `iron_to_bunker_ratio`, `gogl_momentum_30` | 3 |
| Seasonal Indicators | `month`, `quarter`, `is_monsoon`, `is_winter_heating` | 4 |
| **TOTAL** | | **~79 features** |

**Seasonal Logic:**
- `is_monsoon = 1` → June–September (tidal siltation at Haldia, port congestion)
- `is_winter_heating = 1` → November–February (North Asian thermal coal demand peak)

Features are resampled from daily to monthly (`resample("MS").mean()`) before alignment with freight rate fixtures.

---

### B3. Multi-Quantile LightGBM Forecaster (`engine/ml_forecaster.py`)

Three **independent** LightGBM Quantile Regressors are trained per corridor:

| Model | Quantile α | Purpose |
|---|:---:|---|
| `model_p10` | 0.10 | Bearish low — stress scenario |
| `model_p50` | 0.50 | Median forecast — base case |
| `model_p90` | 0.90 | Bullish high — upside scenario |

**LightGBM Hyperparameters:**

```python
{
    "n_estimators": 80,
    "learning_rate": 0.05,
    "max_depth": 4,
    "num_leaves": 15,
    "min_child_samples": 3,
    "subsample": 0.85,
    "random_state": 42,
}
```

**Quantile Monotonicity Guarantee:**

After inference, outputs are sorted row-wise:
```
y_hat_p10 <= y_hat_p50 <= y_hat_p90
```

---

### B4. Forecast Probability & Break-Even Engine

**Implied Standard Deviation from Quantile Spread:**

```
sigma_implied = mean(p90_rates - p10_rates) / 2.5631

Derivation: For standard normal, p90 - p10 = 2 x 1.2816 x sigma = 2.5631 x sigma
```

**Break-Even Spot Rate:**

```
breakeven_rate = (cvc_total_usd - spot_operational_total) / (cargo_tonnage x num_voyages)
```

**Break-Even Probability (Gaussian CDF):**

```
z    = (breakeven_rate - mu_spot) / sigma_implied
prob = scipy.stats.norm.cdf(z)  x  100
```

| Probability | Recommendation |
|---|---|
| < 20% | Lock CVC contract confidently |
| 20–40% | Review CVC terms |
| 40–60% | Scenario-dependent |
| > 60% | Prefer Spot market |

---

## Section C — Financial Evaluation Engine

### Cost Components per Voyage

| Component | Formula |
|---|---|
| Spot Freight | `spot_rate x cargo_tonnage` |
| CVC Freight | `locked_cvc_rate x cargo_tonnage` |
| Bunker Adjustment | `$0.85/T x cargo_tonnage` |
| Port Charges | `$18,500 flat per call` |
| Demurrage | `wait_days x $22,000/day` |
| Lighterage | `lightered_tonnage x $3.50/T` (if Sagar STS triggered) |

### CVC Rate Determination

```python
if target_cvc_rate is not None:
    locked_cvc_rate = target_cvc_rate
else:
    locked_cvc_rate = avg_spot_rate x (1 - cvc_discount_pct / 100)
```

**Currency:** All USD figures converted to INR at `83.50 INR / $1`, expressed in Crores (`1 Cr = 10,000,000 INR`).

---

## Section D — Model Evaluation & Visualization

### Metrics Computed (`engine/evaluator.py`)

| Metric | Formula | Target |
|---|---|:---:|
| MAE | Mean |actual - p50| | Lower is better |
| RMSE | sqrt(Mean(actual - p50)^2) | Lower is better |
| MAPE | Mean|actual-p50|/actual x 100 | < 15% good |
| R^2 Score | 1 - SS_res/SS_tot | Closer to 1.0 |
| Pinball Loss p10 | Quantile loss at alpha=0.10 | Lower is better |
| Pinball Loss p50 | Quantile loss at alpha=0.50 | Lower is better |
| Pinball Loss p90 | Quantile loss at alpha=0.90 | Lower is better |
| 80% PI Coverage | % actuals inside [p10, p90] | ~80% ideal |

### Generated Plots (`reports/plots/`)

| File | Description |
|---|---|
| `forecast_confidence_bands.png` | Time-series with p10/p50/p90 overlay and actual scatter |
| `feature_importance.png` | Top-20 LightGBM gain importances (horizontal bar chart) |
| `break_even_cdf.png` | Gaussian PDF + CDF with break-even threshold annotation |
| `residual_distribution.png` | p50 residual histogram, KDE overlay, and Q-Q normality plot |

All figures use a dark-mode colour theme, saved at 150 DPI using `matplotlib.use("Agg")` for headless safety.

---

## Section E — CLI Interface Reference

```
python cli.py [OPTIONS]
```

| Flag | Description | Example |
|---|---|---|
| `--demo` | Two pre-packaged Ministry demo scenarios | `python cli.py --demo` |
| `--update-data` | Sync live market data to Parquet cache | `python cli.py --update-data` |
| `--train-ml` | Retrain all quantile LightGBM models | `python cli.py --train-ml` |
| `--evaluate` | Compute metrics + save diagnostic plots | `python cli.py --evaluate` |
| `--cargo MT` | Cargo parcel in metric tons (default: 75,000) | `--cargo 150000` |
| `--origin NAME` | Origin load port (default: Newcastle) | `--origin "Hay Point"` |
| `--destination NAME` | Discharge port (default: Haldia) | `--destination Dhamra` |
| `--voyages N` | Number of consecutive voyages (default: 4) | `--voyages 6` |
| `--cvc-discount PCT` | CVC negotiated discount % (default: 5.0) | `--cvc-discount 7.5` |
| `--target-cvc-rate $/T` | Explicit locked CVC rate override | `--target-cvc-rate 18.40` |

### Recommended Workflow

```bash
# Step 1: Sync latest market data
python cli.py --update-data

# Step 2: Retrain models on fresh data
python cli.py --train-ml

# Step 3: Run Ministry presentation scenarios
python cli.py --demo

# Step 4: Run custom evaluation
python cli.py --cargo 120000 --origin "Taboneo" --destination "Vizag" --voyages 5

# Step 5: Generate diagnostic evaluation reports
python cli.py --evaluate
```

---

## Section F — Project Structure

```
SIH_Freight-Forecasting/
│
├── cli.py                         # Main CLI entrypoint
│
├── data/
│   ├── ports.py                   # Indian & international port registry
│   ├── vessels.py                 # Vessel class definitions
│   ├── mock_rates.py              # Operational cost constants & mock rates
│   ├── fetcher.py                 # Parquet cache manager + yfinance sync
│   ├── features.py                # Feature engineering pipeline
│   └── historical/
│       ├── macro_data.parquet
│       ├── route_fixtures.parquet
│       └── models/                # Serialized LightGBM .joblib files
│
├── engine/
│   ├── feasibility.py             # Vessel feasibility & lighterage router
│   ├── financial_evaluator.py     # Spot vs. CVC financial engine
│   ├── ml_forecaster.py           # Multi-Quantile LightGBM forecaster
│   └── evaluator.py               # Metrics computation + diagnostic plots
│
├── tests/
│   ├── test_feasibility.py
│   ├── test_financial_evaluator.py
│   └── test_ml_pipeline.py        # 25 tests (all passing)
│
├── reports/
│   └── plots/                     # Generated PNG diagnostic artefacts
│
├── PORTS_AND_ML_SPEC.md           # This document
└── README.md
```

---

## Appendix: Key Design Decisions

### Why LightGBM over Deep Learning (TFT/PyTorch)?

| Criterion | LightGBM (chosen) | PyTorch TFT |
|---|---|---|
| Training data size | ~37 monthly samples — ideal for trees | Needs 1,000+ samples |
| Interpretability | Native feature importance (gain) | Black-box attention weights |
| Training speed | < 1 second per route | Minutes per route |
| Quantile support | Native `objective="quantile"` | Custom loss required |
| Deployment | Single `.joblib` file | Large model state dict |

### Why Parquet over SQLite / DuckDB?

- Zero schema migration for new time-series columns
- Column-pruned reads via `pyarrow` — only load needed features
- Native Pandas interop (`pd.read_parquet` / `df.to_parquet`)
- Sufficient for this scale (< 5,000 rows); DuckDB adds value only at 100K+ rows

### Why Gaussian CDF for Break-Even Probability?

The quantile spread (p90 - p10) parameterizes a Gaussian per the standard normal relationship. While freight rates are log-normal, the Gaussian CDF provides a **conservative, interpretable probability** suitable for Ministry procurement risk reporting, with sub-millisecond compute via `scipy.stats.norm.cdf`.

---

*Document maintained by the SIH Freight Forecasting Engineering Team.*  
*Last updated: September 2026*
