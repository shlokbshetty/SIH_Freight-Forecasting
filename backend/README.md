# FreightIQ backend

FastAPI service behind the React dashboard. Ingests live market and weather
data, projects freight rates with SARIMAX, and prices chartering decisions.

## Quick start

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python train.py                      # fits the models from the committed snapshot
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/docs. No API key, no account, no network needed for
any of the above except `pip install`.

## The offline guarantee

`data/snapshot.json` is committed. On startup the app seeds its SQLite cache
from it if the cache is empty, so a fresh clone with the network unplugged
still serves every endpoint. `train.py` reads the same cache, so even model
training works offline.

Prove it:

```bash
FREIGHTIQ_OFFLINE=1 uvicorn app.main:app --port 8000
curl -s localhost:8000/api/data/status | python -m json.tool
```

Every source reports `"is_stale": true` and every endpoint still answers.
That is the intended behaviour, not a failure: stale data is surfaced, never
disguised.

## Refreshing the snapshot

The snapshot is a point-in-time export of the ingestion cache. Refresh it
whenever you want the offline baseline to reflect the current market.

```bash
cd backend
source .venv/bin/activate

python scripts/refresh_snapshot.py              # pull live, then export
python scripts/refresh_snapshot.py --days 730   # keep two years instead of three
python scripts/refresh_snapshot.py --skip-fetch # export what is already cached
```

The script pulls every adapter, writes the results into `data/cache.db`, then
exports the cache to `data/snapshot.json` in a columnar format that keeps the
file around 200 KB and diffs sanely.

It **refuses to write if any source came back stale**, so a rate-limited
afternoon cannot quietly degrade the committed baseline. Override with
`--allow-stale` when you know a source is down and want the rest anyway; the
output records `provenance: "live-partial"` when that happens.

Commit the result, then retrain so the pickles match the data:

```bash
python train.py
git add data/snapshot.json models/metrics.json
```

### If you have no market access

`scripts/generate_baseline_snapshot.py` synthesises a calibrated snapshot using
only the standard library. Levels, volatilities and cross-correlations are set
to plausible market values so the model has real signal to fit, but the numbers
are **not** market observations. The file records
`provenance: "synthetic-calibrated"`, and every seeded source is marked stale,
so it cannot be mistaken for live data in the UI.

```bash
python scripts/generate_baseline_snapshot.py --days 1095
```

The snapshot currently committed was produced this way. Replace it with a live
pull before anyone reads a number off it.

## Training

```bash
python train.py                    # all four classes, with backtest
python train.py --classes capesize # one class
python train.py --refresh          # pull live data first
python train.py --no-backtest      # skip scoring, much faster
```

Writes `models/sarimax_<class>.pkl` and `models/metrics.json`. Pickles are
git-ignored and rebuildable; the metrics file is committed because the UI reads
accuracy from it.

Training never happens in a request handler. The API loads the pickles at
startup and calls `SARIMAXResults.apply(..., refit=False)`, which re-runs the
Kalman filter over the newest cached observations using coefficients that were
already estimated. Fresh data, no estimation on the request path.

## Endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/api/ports` | Ports with their berths, lighterage nodes, provenance and live congestion |
| GET | `/api/ports/{port}/berths` | Berths for one port, each with its own source URL and date |
| POST | `/api/match` | Every vessel class run through the berth resolver for this cargo |
| POST | `/api/forecast` | History, forecast, p80 and p95 intervals, drivers, accuracy |
| POST | `/api/contract` | Spot versus consecutive voyage charter, with break-even |
| GET | `/api/data/status` | Per source: `last_fetched`, `is_stale`, `age_minutes`, `is_proxy`, `source_label` |
| POST | `/api/data/refresh` | Force a refresh now |
| GET | `/api/health` | Liveness |

## Ports: berth level, not port level

`data/ports/berths.csv` carries one row per berth: length, beam, draft, the
commodities it handles, its discharge rate, and where the figure came from.
The flat one-draft-per-port table is gone, because a port is not one number.
Paradip's iron ore quay and its central quays are five metres apart, and picking
a ship on the port's headline figure is how vessels end up waiting.

`resolve_berth(port, commodity, vessel_draft, tonnage)` returns the best
eligible berth or a rejection, with three outcomes kept distinct:

| Outcome | Meaning |
|---|---|
| `ACCEPT_ALL_TIDE` | Berths on arrival, no tidal waiting |
| `ACCEPT_HIGH_TIDE_ONLY` | Fits only inside a high-water window, which buys waiting days |
| `REJECT` | Cannot berth as loaded |

The middle one is not a rounding of the first. A tide-bound call is a different
fixture at a different price, and collapsing the two is how tidal waiting ends
up unpriced.

Every rejection names the constraint that actually binds, in order of finality:
commodity first, because no tide fixes a berth with no grab for the cargo; then
length and beam, which cannot be lightered away; draft last, because it is the
only one taking cargo off can fix.

**Visakhapatnam** is two basins in one table. The outer harbour berths carry
about eighteen metres and take iron ore and coking coal; the inner harbour
carries about fourteen and a half and takes thermal coal, fertiliser and general
cargo. There is no `basin` column: the commodity list on each berth already
decides the basin and the draft decides the rest, so a second column could only
disagree with the first.

**Haldia** triggers the lighterage path. Anything over the dock's draft is routed
via Sandheads or Sagar, and the answer that comes back is a costed plan with
tonnes to lighten, barge trips, added days and dollars, not a bare no. The
anchorages live in `lighterage_nodes.csv` and are deliberately not berths:
modelling an anchorage as a berth would let the resolver accept a vessel
somewhere she cannot discharge.

Berth allocation prefers a berth that suits the ship. Not the deepest free one,
which ties up a Capesize quay for a Supramax parcel, and not the tightest one
that technically fits, which leaves nothing for a swell.

> **Verify the numbers before you fix on them.** They are compiled from public
> port-authority material and are indicative. See
> [`data/ports/PROVENANCE.md`](data/ports/PROVENANCE.md).

## Sources, and what stands in for what

Two of these are not the thing their name suggests. Both are flagged `is_proxy`
and both surface that flag through `/api/data/status`, so the dashboard can
label them rather than implying an authority they do not have.

| Adapter | Source | Proxy? | Note |
|---|---|---|---|
| `baltic` | TradingEconomics `BDIY:IND` | yes | A contract-for-difference quote tracking the licensed index. **Not** a Baltic assessment. The Exchange licenses the real thing and there is no free feed. |
| `equity` | Yahoo `GOGL`, `SBLK` | yes | Golden Ocean is Capesize heavy, Star Bulk skews Supramax and Ultramax. Each ticker is probed at startup. |
| `commodity` | Yahoo `MTF=F`, `TIO=F`, FRED `PCOALAUUSDM` | no | Coal API2 and iron ore 62% Fe. Falls back to FRED when a future is empty. |
| `macro` | FRED `DEXINUS`, `DEXUSAL` | no | Rupees per dollar and dollars per Aussie. |
| `bunker` | `data/reference/bunker_vlsfo.csv` | yes | Indicative VLSFO levels for Singapore and Rotterdam. No free bunker feed exists. |
| `congestion` | `data/reference/congestion.json` | yes | Anchorage counts, entered by hand from port-agent reports. |
| `ais` | Static AIS dump on disk | no | Corridor fleet density and per-class draft distributions. Not live. |

**ZIM is excluded from the dry-bulk features.** It is a container liner.
Container and dry bulk are different markets with different demand drivers,
different vessel supply and different cycles; feeding ZIM into a dry-bulk model
imports noise dressed as signal. It is available as a standalone macro sentiment
series behind `FREIGHTIQ_INCLUDE_ZIM=1`, and `models/project.py` never reads it.

**MarineTraffic and VesselFinder are not scraped.** Both prohibit it, both block
bots, and a scraper that works today becomes a silent source of wrong numbers
the day their markup changes. `CongestionAdapter` reads a committed file behind
the same interface, so a licensed feed drops in by replacing one method.

**Monthly series are resampled, not forward-filled.** FRED coal and the bunker
file are monthly. Forward-filling a monthly print holds it flat for thirty-one
days and then steps, handing the model a staircase it reads as a month of calm
followed by a shock. `models/project.py` interpolates in time for any series
whose median gap exceeds twenty days and forward-fills the daily ones, and the
raw monthly prints stay cached alongside.

### Getting the AIS file

`AISAdapter` reads a static AIS position dump, the kind published on Kaggle from
the MarineCadastre archive. Expected columns are `MMSI, BaseDateTime, LAT, LON,
SOG, VesselType, Length, Width, Draft`; anything else is ignored. Drop it at
`data/reference/ais_positions.csv` or point `FREIGHTIQ_AIS_FILE` at it. It is
git-ignored because these files run to hundreds of megabytes.

Without it the adapter reports itself unavailable at startup and everything else
carries on. Note that most public AIS dumps are US coastal and will show zero
vessels in the Indian Ocean corridors; the adapter says so rather than reporting
an empty lane as a quiet one.

### The circularity guard

`freight.rate.<class>`, the series the model forecasts, is derived from these
proxies in `data/ingest.py`. Feeding a class its own driver back in as a
regressor would fit a deterministic identity: flawless in sample, no information,
and a backtest that looks impressive while predicting nothing.

So each class drops the one series that generated its target and keeps the rest.
`project.OWN_DRIVER` and `ingest.CLASS_DRIVERS` must be kept in step, and both
say so at their definitions.

## Failure behaviour

Every adapter is independently failure-tolerant. `SourceAdapter.safe_fetch`
never raises: on any exception it logs a warning, reads that adapter's last
values back out of SQLite, and returns them marked stale. One dead source can
never break ingestion, the API, or a screen.

The same principle runs through the rest:

- A missing or corrupt model pickle logs a warning at startup, and
  `/api/forecast` serves a random-walk fallback labelled `"model":
  "naive-fallback"`.
- A missing `metrics.json` returns `accuracy` with nulls and a note.
- A failed backtest fold is skipped, not fatal.
- If the scheduler cannot start, the app still serves.

## Architecture rule

Nothing in a request path fetches. The scheduler calls `refresh_all` on a timer,
adapters write to SQLite, and API handlers read only from the cache. The
committed snapshot seeds that cache at startup, so a cold boot with no network
serves every screen.

If you are adding a source, it goes in `data/adapters/`, it subclasses
`SourceAdapter`, and it gets registered in `data/adapters/__init__.py`. It does
not get called from a router.

## Notes and known gaps

- **Python version.** Pinned to CPython 3.11 or 3.12. On 3.13+, and certainly
  on 3.14, `statsmodels` and `pandas` wheels may not exist yet and will try to
  build from source. Use `pyenv` or a 3.12 virtualenv.
- **The frontend does not call this yet.** The React app still reads static
  TypeScript from `src/data/`. Wiring it up is a separate piece of work.
- **Reference data is duplicated.** `app/reference.py` mirrors
  `src/data/ports.ts` and `src/data/vessels.ts`. Keep them in step until the
  frontend switches to `/api/ports`.
- **Per-tonne rates were corrected.** The frontend mock has Capesize as the most
  expensive class per tonne and Handysize the cheapest. That is backwards:
  freight per tonne falls as the ship gets bigger, because a Capesize spreads a
  voyage over five times the cargo. The backend uses the correct ordering, so
  the two disagree until the frontend is rewired.
- **Berth figures are indicative.** See
  [`data/ports/PROVENANCE.md`](data/ports/PROVENANCE.md). Declared drafts change
  several times a year as ports dredge and silt; treat the file as perishable.
- **The Baltic adapter will usually fail without a key.** TradingEconomics'
  guest credential does not cover `BDIY:IND`. That is the designed degradation,
  not a bug: it falls back to cache and reports stale. Set
  `TRADINGECONOMICS_KEY` for live values.
- **The committed bunker CSV is monthly and indicative.** Update it by hand, or
  replace `BunkerAdapter.fetch` with a licensed feed. Nothing else changes.
- **`OWN_DRIVER` and `CLASS_DRIVERS` are coupled.** They live in
  `models/project.py` and `data/ingest.py` respectively and must agree. There is
  no test enforcing it yet.
