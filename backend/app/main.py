"""FastAPI application.

Startup order matters and is deliberate:

1. Open the SQLite cache.
2. Seed it from the committed snapshot if it is empty. This is what lets a
   cold, network-free boot serve every screen.
3. Load the pickled projection models and the backtest metrics. A missing
   pickle is a warning, not a failure: the forecast endpoint degrades to a
   random walk and says so.
4. Start the hourly refresh scheduler, unless it is switched off.

Nothing in that sequence requires the network, and nothing in it trains a model.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.deps import AppState, snapshot_provenance
from app.routers import contract, forecast, match, ports, series, status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("freightiq")


def _load_models(state: AppState) -> None:
    from models import project

    for vessel_class in project.VESSEL_CLASSES:
        path = project.model_path(config.MODEL_DIR, vessel_class)
        if not path.exists():
            log.warning("no model pickle at %s; %s will use the fallback", path.name, vessel_class)
            continue
        try:
            state.bundles[vessel_class] = project.ProjectionBundle.load(path)
            log.info("loaded model %s (trained %s)", path.name, state.bundles[vessel_class].trained_at)
        except Exception as exc:  # noqa: BLE001 - a bad pickle must not stop startup
            log.warning("could not load %s: %s", path.name, exc)

    state.metrics = project.read_metrics(config.METRICS_FILE)


def _validate_sources() -> dict[str, list[str]]:
    """Probe every adapter at startup.

    A renamed ticker, a missing file or an absent credential is reported here,
    once, rather than becoming a column of NaNs three layers down in a feature
    frame. Nothing here is fatal: a source that fails validation still degrades
    to cache like any other.
    """
    try:
        from data.adapters import build_adapters, validate_all

        report = validate_all(build_adapters())
        healthy = [name for name, problems in report.items() if not problems]
        log.info("source validation: %s healthy, %s with warnings",
                 len(healthy), len(report) - len(healthy))
        return report
    except Exception as exc:  # noqa: BLE001 - validation must never stop startup
        log.warning("source validation could not run: %s", exc)
        return {}


def _start_scheduler(state: AppState) -> None:
    if not config.SCHEDULER_ENABLED:
        log.info("scheduler disabled by configuration")
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from data import ingest

        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_job(
            lambda: ingest.refresh_all(state.conn),
            "interval",
            minutes=config.REFRESH_INTERVAL_MINUTES,
            id="refresh_all",
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
        state.scheduler = scheduler
        log.info("scheduler started, refreshing every %s minutes", config.REFRESH_INTERVAL_MINUTES)
    except Exception as exc:  # noqa: BLE001 - no scheduler is better than no app
        log.warning("could not start scheduler: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from data import cache, ingest

    state = AppState()
    app.state.freightiq = state

    state.conn = cache.connect(config.CACHE_DB)
    seeded = ingest.bootstrap(state.conn)
    if seeded:
        log.info("seeded %s observations from the committed snapshot", seeded)
    state.snapshot_provenance = snapshot_provenance(config.SNAPSHOT_FILE)

    state.source_report = _validate_sources()
    _load_models(state)

    if config.REFRESH_ON_STARTUP:
        try:
            ingest.refresh_all(state.conn)
        except Exception as exc:  # noqa: BLE001
            log.warning("startup refresh failed: %s", exc)

    _start_scheduler(state)

    try:
        yield
    finally:
        if state.scheduler is not None:
            try:
                state.scheduler.shutdown(wait=False)
            except Exception:  # noqa: BLE001
                pass
        if state.conn is not None:
            state.conn.close()


app = FastAPI(
    title="FreightIQ API",
    version="0.2.0",
    description="Freight forecasting and chartering decisions for East Coast India bulk imports.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(ports.router)
app.include_router(match.router)
app.include_router(forecast.router)
app.include_router(contract.router)
app.include_router(series.router)
app.include_router(status.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "offline_mode": config.OFFLINE_MODE}
