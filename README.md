# FreightIQ

Freight forecasting and vessel-chartering optimisation for bulk imports into
India's East Coast ports. Smart India Hackathon problem statement 26006.

An importer buying coal into Paradip, Visakhapatnam, Gangavaram, Dhamra,
Gopalpur or Haldia currently fixes ships one voyage at a time and takes whatever
the market is that week. This moves that decision from reactive to priced: it
forecasts where freight is going, works out which ship can actually berth where,
and puts a rupee figure on locking a multi-voyage contract against staying on
spot.

## Running it

Two processes. The dashboard works on its own, with the data bundled into the
build; the backend adds live ingestion, fitted forecasts and berth-level port
data.

```bash
# Frontend
npm install
npm run dev                       # http://localhost:5173

# Backend, in another shell
cd backend
python -m venv .venv && source .venv/bin/activate   # CPython 3.11 or 3.12
pip install -r requirements.txt
python train.py                                     # fits from the committed snapshot
uvicorn app.main:app --reload --port 8000           # http://localhost:8000/docs
```

Point the dashboard elsewhere with `VITE_API_BASE` in a `.env` file. It defaults
to `http://localhost:8000`.

**Every screen renders with the backend down.** The client falls back to the
data bundled with the app and shows a badge saying so. That mirrors the
backend's own rule, where a dead source degrades to cached values rather than an
error. What is never acceptable is showing stale or bundled numbers as though
they were live, so both states are labelled.

## What is in the dashboard

| Screen | What it answers |
|---|---|
| **Command Center** | What the market did today, which ports are queuing, where to go next |
| **Route Map** | Which ports this vessel class can berth at, with trade lanes, weather and fleet density |
| **Forecast** | Where rates are going, with 80% and 95% bands, driver attribution and backtest accuracy |
| **Vessel Matcher** | Which class berths at which berth for this cargo, and what lighterage costs |
| **Contract Simulator** | Spot against consecutive voyage charter against period time charter, with break-even and multi-port discharge |
| **Market Timing** | Which week to fix, and what waiting costs the programme |
| **Idle & Ballast** | Turnaround by port, and the cheapest ballast leg to the next cargo |
| **Risk & Data Health** | Disruptions derived from live data, and the freshness of every source behind it |

## Ports are modelled at berth level

Not one draft per port. Paradip's iron ore quay and its central quays are five
metres apart, and picking a ship on the port's headline figure is how vessels end
up waiting. Every berth carries its length, beam, draft, tidal allowance,
commodities, discharge rate and a source URL, and the resolver answers three
ways: berths on arrival, berths only on the tide, or cannot berth. The middle
answer is a different fixture at a different price, so it is kept distinct.

Anything too deep for Haldia routes through the Sandheads lighterage path and
comes back as a costed plan, not a refusal.

> Berth figures are compiled from public port-authority material and are
> indicative. See [`backend/data/ports/PROVENANCE.md`](backend/data/ports/PROVENANCE.md)
> before quoting one.

## Stack

React 19, TypeScript, Vite, Recharts, Leaflet on the front. FastAPI, pandas,
statsmodels and SQLite on the back. CPU only, no paid API keys, no GPU.

---

## Backend (FastAPI)

The Python service in [`backend/`](backend/) provides live data ingestion,
freight-rate projection, and the chartering endpoints the dashboard consumes.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # use CPython 3.11 or 3.12
pip install -r requirements.txt
python train.py                                     # fits from the committed snapshot
uvicorn app.main:app --reload --port 8000
```

Endpoints: `/api/ports`, `/api/ports/{port}/berths`, `/api/match`,
`/api/forecast`, `/api/contract`, `/api/data/status`. Interactive docs at
http://localhost:8000/docs.

Ports are modelled at berth level: length, beam, draft, commodities, discharge
rate and a source URL per berth. The resolver answers three ways, separating
"berths on arrival" from "berths only on the tide", and routes anything too deep
for Haldia through the Sandheads lighterage path with costed days and dollars.

### Working offline

`backend/data/snapshot.json` is committed and seeds the cache on first boot, so
a fresh clone serves every screen with no network at all. Training reads the
same cache, so that works offline too.

```bash
FREIGHTIQ_OFFLINE=1 uvicorn app.main:app --port 8000
```

### Refreshing the snapshot

```bash
cd backend
python scripts/refresh_snapshot.py     # pull live sources, then export the cache
python train.py                        # retrain so the pickles match the data
git add data/snapshot.json models/metrics.json
```

The script refuses to overwrite a good snapshot if any source came back stale;
pass `--allow-stale` to override. With no market access at all,
`scripts/generate_baseline_snapshot.py` synthesises a calibrated stand-in using
only the standard library.

Full detail, including which ticker proxies which vessel class and what the
stub adapters do, is in [`backend/README.md`](backend/README.md).
