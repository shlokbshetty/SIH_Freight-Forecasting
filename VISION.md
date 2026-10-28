# FreightIQ Architectural Vision

## 1. Mission Statement

India's steel mills, thermal power utilities, and fertilizer importers move hundreds of millions of tonnes of dry-bulk cargo through East Coast ports (**Paradip, Visakhapatnam, Gangavaram, Dhamra, Gopalpur, and Haldia**). Chartering desks face three tightly coupled decisions on every stem:
1. **Where will the market rate be** across the next 30 to 180 days?
2. **Which berth can physically accept the vessel**—on all tides, on high water only, or only after costly anchorage lighterage at Sandheads/Sagar?
3. **Should the programme be fixed on the Spot market, locked into a Consecutive Voyage Charter (CVC), or hired on a Period Time Charter (PTC)?**

**FreightIQ** is built on the vision that **maritime freight forecasting and physical berth resolution cannot be solved in isolation**: a cheap Capesize rate per tonne is worthless if draft restrictions at Haldia or inner-harbour Visakhapatnam consume the savings in lighterage barges and tidal demurrage.

---

## 2. Core Architectural Pillars

### Pillar 1: Berth-Level Physics Over Port-Level Averages
Most maritime dashboards model a port as a single maximum draft number. In reality, ships berth at specific quays with distinct drafts, lengths, beams, and grab equipment (`backend/data/ports/berths.csv`). FreightIQ resolves compatibility at the individual berth level and keeps `ACCEPT_ALL_TIDE`, `ACCEPT_HIGH_TIDE_ONLY`, and `REJECT` (with costed lighterage plans) commercially distinct so tidal waiting and barge transfers are explicitly priced into every fixture.

### Pillar 2: Econometric Honesty & Provenance Transparency
- **No Circular Regressors**: `OWN_DRIVER` guarantees a vessel class never uses its own generating proxy as an exogenous predictor.
- **No Staircase Artifacts**: Sparse monthly series are time-interpolated (`_densify`) rather than forward-filled.
- **No Disguised Proxies or Stale Data**: Every proxy feed (`is_proxy=True`) and cached observation (`is_stale=True`) is surfaced through `/api/data/status` and `DataOriginNotice` in the UI. Berth limits carry explicit port-authority `source_url` and `source_date` provenance (`PROVENANCE.md`).

### Pillar 3: Zero-Failure Offline Resilience
Whether deployed in a port operations center with intermittent internet or evaluated on an air-gapped machine, FreightIQ never fails on a network outage. Request handlers never touch the network; `cache.db` self-seeds from the committed `snapshot.json`; missing model pickles degrade to a labeled random-walk projection (`naive-fallback`); and the React client falls back to local reference calculations (`src/lib/fallbacks.ts`) if the API server is offline.
