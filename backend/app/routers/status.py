"""GET /api/data/status - per-source freshness."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app import config
from app.deps import AppState, get_state, utcnow
from app.schemas import DataStatusResponse
from data import cache

router = APIRouter(prefix="/api/data", tags=["data"])


@router.get("/status", response_model=DataStatusResponse)
def data_status(state: AppState = Depends(get_state)) -> DataStatusResponse:
    """What each adapter last managed, and how old it is.

    Reports every adapter that has ever run, including ones currently failing,
    so a dead source is visible in the UI rather than silently serving stale
    numbers as though they were live.
    """
    sources = cache.read_status(state.conn, config.STALE_AFTER_MINUTES)

    # A source that has never run at all has no status row, so it would be
    # invisible rather than reported broken. Fill the gaps from the registry.
    from data.adapters import adapter_metadata

    seen = {s["source"] for s in sources}
    for name, info in adapter_metadata().items():
        if name not in seen:
            sources.append(
                {
                    "source": name, "last_fetched": None, "last_success": None,
                    "is_stale": True, "age_minutes": None, "row_count": 0,
                    "error": "never fetched", "is_proxy": info["is_proxy"],
                    "source_label": info["source_label"], "notes": [],
                }
            )
    # Fold in whatever startup validation found, so a renamed ticker or a
    # missing credential is visible in the same place as staleness.
    for row in sources:
        problems = state.source_report.get(row["source"]) or []
        if problems:
            row["notes"] = list(row.get("notes") or []) + problems

    sources.sort(key=lambda s: s["source"])

    return DataStatusResponse(
        as_of=utcnow(),
        offline_mode=config.OFFLINE_MODE,
        stale_after_minutes=config.STALE_AFTER_MINUTES,
        snapshot_provenance=state.snapshot_provenance,
        sources=sources,
    )


@router.post("/refresh")
def refresh_now(state: AppState = Depends(get_state)) -> dict:
    """Force a refresh. Handy in a demo; the scheduler does this hourly anyway."""
    from data import ingest

    outcomes = ingest.refresh_all(state.conn)
    return {
        "as_of": utcnow(),
        "results": [
            {"source": o.adapter, "rows": o.rows, "is_stale": o.is_stale, "error": o.error}
            for o in outcomes
        ],
    }
