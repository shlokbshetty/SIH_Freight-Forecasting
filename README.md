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
| **Evaluate (CVC)** | The evaluator page: a quick spot against CVC read with quantile rates |
| **Route Map** | Which ports this vessel class can berth at, with trade lanes, weather and fleet density |
| **Forecast** | Where rates are going, with 80% and 95% bands, driver attribution and backtest accuracy |
| **Vessel Matcher** | Which class berths at which berth for this cargo, and what lighterage costs |
| **Contract Simulator** | Spot against consecutive voyage charter against period time charter, with break-even and multi-port discharge |
| **Market Timing** | Which week to fix, and what waiting costs the programme |
| **Idle & Ballast** | Turnaround by port, and the cheapest ballast leg to the next cargo |
| **Risk & Data Health** | Disruptions derived from live data, and the freshness of every source behind it |
| **Voyage Editor** | Edit a matched voyage and lock a charter, reached from the Vessel Matcher |

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

Dark and light themes, both token-driven. React 19, TypeScript, Vite, Recharts, Leaflet on the front. FastAPI, pandas,
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

---

## The vocabulary

**The commercial terms, which is most of it**

| Term | What it means |
|---|---|
| Charter | Hiring a ship. The owner owns it, the charterer hires it. |
| Charterer | Here, the Indian buyer hiring ships to bring coal in. |
| Fixture | A concluded charter deal. To "fix" a ship is to agree one. |
| Spot | Hiring for a single voyage at today's market rate. |
| Voyage charter | Owner carries cargo from A to B for a rate per tonne and pays the crew, fuel and port costs out of it. |
| CVC, Consecutive Voyage Charter | One contract covering a run of back to back voyages at one agreed rate. The subject of the simulator. |
| Time charter | Hiring the ship itself for a period at a daily hire rate. The charterer directs it and buys the fuel. |
| Laycan | Laydays and cancelling. The window in which the ship must show up to load. |
| Laytime | The free time allowed for loading and discharging before the clock starts costing money. |
| Demurrage | What the charterer pays the owner, per day, when the ship is held beyond laytime. |
| Despatch | The reverse of demurrage. The owner pays the charterer for finishing early. |
| Laden | Loaded with cargo. |
| Ballast | Sailing empty, carrying seawater for stability. The return leg of most voyages. |
| Deadheading | Running empty without earning. What the repositioning module is meant to minimise. |
| Bunkers | The ship's fuel. Bunkering is refuelling. |
| Lighterage | Taking cargo off a big ship into barges at an anchorage, so it floats higher and can enter a shallow port. |
| Transshipment | Moving cargo from one vessel to another before it reaches the final berth. |
| Anchorage | A marked sea area where ships anchor to wait or to work cargo. |
| Berth | The spot at the quay where a ship ties up. |
| Tidal window | The period around high tide when a deep ship can safely cross a shallow approach. |
| Congestion | The queue of ships waiting for a free berth. |
| Dry bulk | Unpackaged commodity carried loose in the hold. Coal, iron ore, grain, bauxite. |

**The measurements**

| Short form | Full name | What it does here |
|---|---|---|
| DWT | Deadweight tonnage | Total weight a ship can carry. Defines the size classes. |
| LOA | Length overall | The ship's full length. Berths have a hard limit on it. |
| Beam | Beam | The ship's width. |
| Draft | Draft, or draught | How deep the hull sits below the waterline. Loaded ships sit deeper. |
| UKC | Under keel clearance | The water gap between the keel and the seabed that a port insists on. |
| TPC | Tonnes per centimetre immersion | How many tonnes change the draft by one centimetre. Converts a depth shortfall into a lighterage tonnage. |
| MT, T | Metric tonne | One thousand kilograms. Freight is quoted in dollars per tonne. |
| TPD | Tonnes per day | How fast a port can load or discharge. |
| nm | Nautical mile | Sea distance. One nautical mile is 1,852 metres. |
| kt | Knot | One nautical mile per hour. |
| TAT | Turn around time | Arrival to departure, including the wait for a berth. |
| VLSFO | Very low sulphur fuel oil | The standard marine fuel since the sulphur cap of 2020. |
| BAF | Bunker adjustment factor | A clause that shares fuel price moves between owner and charterer against an agreed basis price. |

**The ship classes, smallest to largest**

| Class | Roughly | Why the name, and where it fits |
|---|---|---|
| Handysize | 28k to 40k DWT | Small and flexible. Gets into almost every East Coast port, including the shallow ones. |
| Supramax | 50k to 60k DWT | The workhorse. Usually carries its own cranes, so it does not need shore equipment. |
| Panamax | 65k to 80k DWT | Built to the width of the original Panama Canal locks. |
| Capesize | 100k DWT and up | Too big for the canals historically, so it sailed round the Cape of Good Hope. Only the deepest Indian ports take it. |

**The market**

| Short form | Full name | What it is |
|---|---|---|
| BDI | Baltic Dry Index | A daily composite of dry bulk freight rates published by the Baltic Exchange in London. The headline barometer for the trade. |
| BPI | Baltic Panamax Index | The Panamax slice of the same family. There are Capesize, Supramax and Handysize equivalents. |
| Forward curve | Forward curve | What the market currently believes future freight will cost. |
| FFA | Forward freight agreement | The traded contract used to hedge freight, the instrument behind a forward curve. |

**The ports in the data**

Discharge, all East Coast India: Paradip and Dhamra and Gopalpur in Odisha, Visakhapatnam and Gangavaram in Andhra Pradesh, Haldia in West Bengal, and Sagar or Sandheads, which is not a port but the anchorage at the mouth of the Hooghly where ships lighten before going upriver. Gangavaram is the deepest. Haldia and Gopalpur are the shallow problem children.

Loading: Newcastle, Gladstone and Abbot Point in Australia, Hampton Roads in the United States, Beira and Nacala in Mozambique, Murmansk in Russia, Kalimantan and Balikpapan in Indonesia.

**The statistics inside the engine**

| Term | What it does |
|---|---|
| Confidence interval | The band around a forecast. Here it is a 90% band, meaning the true rate should land inside it nine times in ten. |
| Standard deviation | How wide the spread of possible outcomes is. |
| CDF, cumulative distribution function | Gives the probability of landing below a given value. This is what produces the "chance spot wins" figure. |
| PDF, probability density function | The height of the bell curve. It draws the shape on the break-even chart. |
| Mean reversion | The tendency of freight rates to get pulled back toward a normal level rather than wandering forever. |
| Haversine | The formula for distance between two points on a sphere, used for sailing distance from port coordinates. |
| Correlation | How much forecast errors in different months move together. Set high here, because they do. |

**The rest**

AIS is the Automatic Identification System, the transponder every commercial ship broadcasts its position on, and the basis of any live vessel tracking. GIS means geographic information system, in practice the map. SIH is the Smart India Hackathon, and this is problem statement 26006. A crore is ten million rupees, written Cr, and a lakh is one hundred thousand. On the software side it is React with TypeScript, built by Vite, charts by Recharts, map by Leaflet, icons by Lucide, linting by oxlint.

---

## Datasets

`data/` holds reference material contributed alongside the dashboard. It is data,
not code, and nothing in the running service depends on it:

| File | What it is |
|---|---|
| `Old_Data_Baltic_Dry_Index.csv` | Real Baltic Dry Index, 1985 to 2013. Predates the window the app models, so it is for backtesting rather than live use. |
| `World Port Index WPI.csv` | The NGA world port register, with channel, anchorage and pier depths. The reference to verify `backend/data/ports/berths.csv` against. |
| `Ship_Performance_Dataset.csv` | Vessel performance observations. |
| `historical/` | Parquet time series and trained quantile models from the retired evaluator engine, kept for reference. |

## History

An earlier branch shipped a second backend: a FastAPI app at the repository root
with an `engine/` package, a LightGBM quantile forecaster and a Parquet fetcher.
It has been retired in favour of the service in `backend/`, which covers the same
ground with berth-level port constraints, fail-soft ingestion and SARIMAX
forecasts, and carries its own test suite.

Two things survived that retirement rather than being deleted with it. The
Evaluate page still works: `backend/app/routers/evaluate.py` answers
`POST /api/evaluate` and `GET /api/ports/catalog` in the shape that page expects.
And the economic invariants from its property tests were ported to
`backend/tests/test_economics.py`, where they now guard this engine instead.
