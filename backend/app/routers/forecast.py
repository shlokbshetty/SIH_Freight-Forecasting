"""POST /api/forecast - projected freight rates with intervals and drivers."""

from __future__ import annotations

import logging

import numpy as np
from fastapi import APIRouter, Depends, HTTPException

from app.deps import AppState, get_state, stale_sources, utcnow
from app.schemas import ForecastRequest, ForecastResponse
from models import project

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["forecast"])

#: What-if keys accepted from the client, mapped onto model features. Client
#: sends natural units, the model works in logs.
SCENARIO_KEYS = {
    "bdi": ("log_bdi", True),
    "bunker": ("log_bunker", True),
    "coal": ("log_coal", True),
    "iron_ore": ("log_iron_ore", True),
    "usdinr": ("log_usdinr", True),
    "monsoon": ("monsoon", False),
}


def _translate_scenario(scenario: dict[str, float] | None) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in (scenario or {}).items():
        mapped = SCENARIO_KEYS.get(key)
        if not mapped:
            continue
        feature, take_log = mapped
        out[feature] = float(np.log(max(float(value), 1e-6))) if take_log else float(value)
    return out


def _naive_projection(frame, steps: int) -> dict:
    """Fallback when no pickle has been trained yet.

    Carries the last observation forward and widens the band with the square
    root of horizon, which is what a random walk does. Clearly labelled in the
    response so nobody mistakes it for the fitted model.
    """
    import pandas as pd

    last = float(frame["rate"].iloc[-1])
    daily_sd = float(frame["log_rate"].diff().dropna().std() or 0.01)
    idx = pd.date_range(frame.index[-1] + pd.Timedelta(days=1), periods=steps, freq="D")
    dates = [d.date().isoformat() for d in idx]

    def band(z: float) -> list[dict]:
        return [
            {
                "date": d,
                "lower": round(last * float(np.exp(-z * daily_sd * np.sqrt(i + 1))), 3),
                "upper": round(last * float(np.exp(z * daily_sd * np.sqrt(i + 1))), 3),
            }
            for i, d in enumerate(dates)
        ]

    return {
        "forecast": [{"date": d, "value": round(last, 3)} for d in dates],
        "intervals": {"p80": band(1.2816), "p95": band(1.9600)},
    }


@router.post("/forecast", response_model=ForecastResponse)
def post_forecast(req: ForecastRequest, state: AppState = Depends(get_state)) -> ForecastResponse:
    vessel_class = req.vessel_class.lower()
    notes: list[str] = []

    try:
        frame = project.build_feature_frame(state.conn, vessel_class)
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"no cached observations for {req.vessel_class}: {exc}",
        ) from exc

    history_tail = frame.iloc[-req.history_days :]
    history = [
        {"date": ts.date().isoformat(), "value": round(float(v), 3)}
        for ts, v in zip(history_tail.index, history_tail["rate"])
    ]

    bundle = state.model_for(vessel_class)
    drivers: list[dict] = []
    model_label = "sarimax"

    if bundle is None:
        notes.append("No trained model for this class. Run train.py; serving a random-walk fallback.")
        model_label = "naive-fallback"
        result = _naive_projection(frame, max(project.HORIZONS))
    else:
        try:
            result = project.forecast(
                bundle, frame,
                horizons=project.HORIZONS,
                scenario=_translate_scenario(req.scenario),
            )
            level = float(result["_point"][min(req.horizon_days, len(result["_point"])) - 1])
            drivers = project.driver_contributions(
                bundle, frame, result["_exog"], level_usd=level, horizon=req.horizon_days
            )
        except Exception as exc:  # noqa: BLE001 - a bad model must not take out the screen
            log.warning("projection failed for %s (%s); falling back", vessel_class, exc)
            notes.append(f"Projection failed ({type(exc).__name__}); serving a random-walk fallback.")
            model_label = "naive-fallback"
            result = _naive_projection(frame, max(project.HORIZONS))

    horizon = req.horizon_days
    forecast = result["forecast"][:horizon]
    intervals = {name: points[:horizon] for name, points in result["intervals"].items()}

    class_metrics = (state.metrics.get("classes") or {}).get(vessel_class) or {}
    horizon_scores = (class_metrics.get("horizons") or {}).get(str(horizon)) or {}
    accuracy = {
        "mape": horizon_scores.get("mape"),
        "rmse": horizon_scores.get("rmse"),
        "folds": horizon_scores.get("folds"),
        "horizon_days": horizon,
        "backtest": state.metrics.get("backtest"),
    }
    if accuracy["mape"] is None:
        notes.append("No backtest scores yet. Run train.py to populate models/metrics.json.")

    if req.scenario:
        notes.append(f"What-if applied: {req.scenario}")

    # Say which regressors were unavailable, rather than letting a neutralised
    # column look like a real reading of zero effect.
    if frame.attrs.get("missing_features"):
        notes.append(
            "regressors unavailable and neutralised: "
            + ", ".join(frame.attrs["missing_features"])
        )

    # The rate this class targets is derived from one proxy, which is therefore
    # excluded from its own regressors. Worth saying once in the payload.
    own = project.OWN_DRIVER.get(vessel_class)
    if own and bundle is not None:
        notes.append(f"{own} excluded from this class's regressors: it derives the target")

    return ForecastResponse(
        vessel_class=req.vessel_class,
        history=history,
        forecast=forecast,
        intervals=intervals,
        drivers=drivers,
        accuracy=accuracy,
        as_of=utcnow(),
        sources_stale=stale_sources(state.conn),
        model=model_label,
        notes=notes,
    )
