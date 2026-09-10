"""Freight rate projection.

A SARIMAX model per vessel class, fitted on the log of the per-tonne route rate
with exogenous regressors for bunkers, the two demand commodities, and
seasonality.

Design notes worth knowing before changing anything here:

*Why log space.* Freight is multiplicative and strictly positive. Modelling the
log keeps the prediction intervals from crossing zero at long horizons and makes
the exogenous coefficients read as elasticities.

*Why Fourier terms and not a seasonal order.* The seasonality that matters is
annual. ``seasonal_order=(P, D, Q, 365)`` on a daily series is not tractable on
CPU. A pair of annual Fourier terms carried as exogenous regressors captures the
same shape for two parameters, which is the standard treatment for long seasonal
periods. The monsoon flag rides alongside it because the monsoon effect is a
step, not a smooth wave.

*Why apply() and not fit() at request time.* Training happens in train.py and is
pickled. The API loads the pickle and calls ``SARIMAXResults.apply(..., refit=
False)``, which re-runs the Kalman filter over the latest cached observations
using the already-estimated coefficients. Fresh data, no estimation, no training
in a request handler.
"""

from __future__ import annotations

import json
import logging
import pickle
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

VESSEL_CLASSES = ["handysize", "supramax", "panamax", "capesize"]

#: Months of the south-west monsoon over the Bay of Bengal.
MONSOON_MONTHS = {6, 7, 8, 9}

#: Exogenous regressors, in a fixed order. The order is part of the pickle
#: contract: a model trained on one ordering cannot be applied to another.
FEATURES: list[str] = [
    "log_bdi",
    "log_gogl",
    "log_sblk",
    "log_bunker",
    "log_coal",
    "log_iron_ore",
    "log_usdinr",
    "monsoon",
    "month_sin",
    "month_cos",
]

#: Human labels for the drivers block in the API response.
FEATURE_LABELS: dict[str, str] = {
    "log_bdi": "Baltic Dry Index (CFD proxy)",
    "log_gogl": "Golden Ocean equity",
    "log_sblk": "Star Bulk equity",
    "log_bunker": "Bunker price (VLSFO Singapore)",
    "log_coal": "Thermal coal (API2)",
    "log_iron_ore": "Iron ore (62% Fe)",
    "log_usdinr": "USD/INR",
    "monsoon": "Monsoon season",
    "month_sin": "Annual seasonality",
    "month_cos": "Annual seasonality",
}

#: Which cached metric fills each column. First hit wins, so a column can fall
#: back when its preferred series is missing.
FEATURE_METRICS: dict[str, list[str]] = {
    "log_bdi": ["baltic.bdi"],
    "log_gogl": ["equity.gogl"],
    "log_sblk": ["equity.sblk"],
    "log_bunker": ["bunker.vlsfo.singapore", "bunker.vlsfo.rotterdam"],
    "log_coal": ["commodity.coal.api2", "commodity.coal.au_daily", "commodity.coal.newcastle"],
    "log_iron_ore": ["commodity.iron_ore.62fe"],
    "log_usdinr": ["macro.usdinr"],
}

#: Columns that come from the calendar and are therefore known in advance.
CALENDAR_FEATURES = ("monsoon", "month_sin", "month_cos")

#: The circularity guard.
#:
#: ``freight.rate.<class>`` is DERIVED from one of these proxies in
#: data/ingest.py. Feeding a class its own driver back in as a regressor fits a
#: deterministic identity: flawless in sample, no information, and a backtest
#: that looks impressive while predicting nothing. Each class therefore drops
#: the one series that generated its target and keeps the rest, which still
#: carry real cross-sectional signal.
#:
#: Keep this in step with CLASS_DRIVERS in data/ingest.py.
OWN_DRIVER: dict[str, str] = {
    "capesize": "log_gogl",
    "panamax": "log_bdi",
    "supramax": "log_sblk",
    "handysize": "log_sblk",
}


def exog_features_for(vessel_class: str) -> list[str]:
    """Regressors for one class, with that class's own driver removed."""
    excluded = OWN_DRIVER.get(vessel_class.lower())
    return [f for f in FEATURES if f != excluded]


#: ZIM is deliberately absent. It is a container liner and does not belong in a
#: dry-bulk model; data/adapters/equity.py keeps it as optional macro sentiment.


DEFAULT_ORDER = (1, 1, 1)
HORIZONS = (30, 90, 180)

#: The default of 50 is not enough for nine regressors plus an ARIMA term: every
#: class stopped exactly at the cap rather than at a converged optimum.
MAX_ITER = 500


# ── Feature frame ─────────────────────────────────────────────────────────────
def _wide_frame(conn: sqlite3.Connection, metrics: list[str]) -> pd.DataFrame:
    from data import cache  # local import keeps models/ importable on its own

    rows = cache.read_observations(conn, metrics=metrics)
    if not rows:
        return pd.DataFrame()
    long = pd.DataFrame(
        {
            "timestamp": pd.to_datetime([r["timestamp"] for r in rows]),
            "metric": [r["metric"] for r in rows],
            "value": [float(r["value"]) for r in rows],
        }
    )
    return long.pivot_table(index="timestamp", columns="metric", values="value", aggfunc="last").sort_index()


def _densify(wide: pd.DataFrame, full_index: pd.DatetimeIndex) -> pd.DataFrame:
    """Put every series on a daily index, choosing the fill per series.

    Daily market series are carried forward over weekends and holidays, because
    no trade happened and the last price is the price.

    Sparse series are interpolated in time instead. The FRED coal series and the
    committed bunker file are monthly, and forward-filling a monthly print holds
    it flat for thirty-one days and then steps, handing the model a staircase it
    reads as a month of calm followed by a shock. Interpolating spreads the move,
    which is closer to how the market actually got between prints.
    """
    out = pd.DataFrame(index=full_index)
    for column in wide.columns:
        series = wide[column].dropna()
        if series.empty:
            continue
        gaps = series.index.to_series().diff().dt.days.dropna()
        median_gap = float(gaps.median()) if len(gaps) else 1.0
        reindexed = series.reindex(series.index.union(full_index))
        filled = (
            reindexed.interpolate(method="time", limit_direction="both")
            if median_gap > 20
            else reindexed.ffill()
        )
        out[column] = filled.reindex(full_index)
    return out


def add_seasonality(frame: pd.DataFrame) -> pd.DataFrame:
    """Month-of-year seasonality as a Fourier pair, plus the monsoon step.

    The raw month number is deliberately not used as a linear regressor: it
    would tell the model that December is twelve times January and that the step
    from December to January is a fall of eleven.
    """
    idx = frame.index
    day_of_year = idx.dayofyear.to_numpy(dtype=float)
    frame["month_sin"] = np.sin(2 * np.pi * day_of_year / 365.25)
    frame["month_cos"] = np.cos(2 * np.pi * day_of_year / 365.25)
    frame["monsoon"] = idx.month.isin(MONSOON_MONTHS).astype(float)
    return frame


def _seeded_metrics(conn: sqlite3.Connection, metrics: list[str]) -> set[str]:
    """Metrics whose newest row still comes from the committed snapshot."""
    from data import cache

    out: set[str] = set()
    for metric in set(metrics):
        row = cache.latest_observation(conn, metric)
        if row is not None and str(row["source"]).startswith("synthetic:"):
            out.add(metric)
    return out


def _pick_metric(candidates: list[str], dense: pd.DataFrame, seeded: set[str]) -> str | None:
    """Choose which cached series fills a feature column.

    A live series beats a seeded one even when the seeded one is listed first.
    Order alone would have fed the model a synthetic coal price while a real
    FRED series sat unused in the same cache, purely because the dead futures
    symbol was named first in the candidate list.
    """
    available = [m for m in candidates if m in dense and dense[m].notna().any()]
    if not available:
        return None
    live = [m for m in available if m not in seeded]
    return (live or available)[0]


def build_feature_frame(conn: sqlite3.Connection, vessel_class: str) -> pd.DataFrame:
    """Daily frame of the target and every regressor, joined and densified.

    Returns all of FEATURES, so the frame is the one the brief describes. Which
    of them a given class regresses on is decided by :func:`exog_features_for`,
    which drops that class's own driver.
    """
    vessel_class = vessel_class.lower()
    target_metric = f"freight.rate.{vessel_class}"

    wanted = [target_metric]
    for candidates in FEATURE_METRICS.values():
        wanted.extend(candidates)

    wide = _wide_frame(conn, wanted)
    if wide.empty or target_metric not in wide:
        raise ValueError(f"no observations for {target_metric}; seed the cache first")

    full_index = pd.date_range(wide.index.min(), wide.index.max(), freq="D")
    dense = _densify(wide, full_index)

    frame = pd.DataFrame(index=full_index)
    frame["rate"] = dense[target_metric]
    frame["log_rate"] = np.log(frame["rate"].clip(lower=1e-6))

    missing: list[str] = []
    seeded = _seeded_metrics(conn, wanted)
    for column, candidates in FEATURE_METRICS.items():
        chosen = _pick_metric(candidates, dense, seeded)
        if chosen is None:
            missing.append(column)
            continue
        frame[column] = np.log(dense[chosen].clip(lower=1e-9))

    if missing:
        # Neutralise a missing regressor at zero rather than dropping the column:
        # the pickle's feature order is part of its contract.
        log.warning("regressors unavailable, neutralised: %s", ", ".join(missing))
        for column in missing:
            frame[column] = 0.0

    frame = add_seasonality(frame)
    frame = frame.dropna()
    if len(frame) < 120:
        raise ValueError(f"only {len(frame)} usable rows for {vessel_class}; need at least 120")
    frame.index.name = "date"
    frame.attrs["missing_features"] = missing
    frame.attrs["vessel_class"] = vessel_class
    return frame



def future_exog(
    frame: pd.DataFrame,
    steps: int,
    scenario: dict[str, float] | None = None,
    features: list[str] | None = None,
) -> pd.DataFrame:
    """Regressor values over the forecast window.

    Commodity and bunker levels are carried forward at their last observation,
    so a forecast reads as "if today's input prices persist". Seasonality is
    computed from the calendar, because it is known. ``scenario`` overrides a
    level for the whole window, which is the hook a what-if slider hangs on:
    pass ``{"log_bunker": log(800)}`` to reprice at eight hundred dollar fuel.
    """
    last = frame.index[-1]
    idx = pd.date_range(last + pd.Timedelta(days=1), periods=steps, freq="D")
    out = pd.DataFrame(index=idx)

    wanted = features or FEATURES
    for name in wanted:
        if name in CALENDAR_FEATURES or name not in frame.columns:
            continue
        out[name] = float(frame[name].iloc[-1])
    out = add_seasonality(out)

    for name, value in (scenario or {}).items():
        if name in out.columns:
            out[name] = float(value)

    for name in wanted:
        if name not in out.columns:
            out[name] = 0.0
    return out[wanted]


def standardise(frame: pd.DataFrame, features: list[str], mean: pd.Series, std: pd.Series) -> pd.DataFrame:
    """Z-score the regressors against the training window's mean and spread.

    Not cosmetic. The raw columns span log-BDI around 7.4 and a monsoon flag of
    zero or one, which leaves the exog matrix with a condition number over a
    thousand; the optimiser walks into its iteration cap and stops at whatever
    it had. Standardised, the same matrix conditions at about twenty and the fit
    converges.

    It also makes the coefficients comparable: each is the effect of a one
    standard deviation move in its own regressor, which is what the drivers
    panel needs to rank them honestly.
    """
    safe_std = std.replace(0.0, 1.0)
    return (frame[features] - mean[features]) / safe_std[features]


# ── Fitting ───────────────────────────────────────────────────────────────────

@dataclass
class ProjectionBundle:
    """What train.py pickles and the API loads at startup."""

    vessel_class: str
    order: tuple[int, int, int]
    features: list[str]
    results: object                      # statsmodels SARIMAXResults
    trained_at: str
    train_rows: int
    train_end: str
    aic: float
    #: Training-window mean and standard deviation of each regressor. Part of the
    #: pickle: applying the model to new data without them would feed the filter
    #: a different scale from the one it was estimated on.
    exog_mean: object = None
    exog_std: object = None
    converged: bool = True
    metrics: dict = field(default_factory=dict)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            pickle.dump(self, fh, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def load(path: Path) -> "ProjectionBundle":
        with path.open("rb") as fh:
            return pickle.load(fh)


def model_path(model_dir: Path, vessel_class: str) -> Path:
    return model_dir / f"sarimax_{vessel_class.lower()}.pkl"


def _fit_with_warm_start(model, label: str):
    """Fit, and if the gradient method stalls, restart it from a simplex search.

    L-BFGS descends badly on a near-flat likelihood, which is what correlated
    freight regressors produce. A few hundred Nelder-Mead steps land close enough
    that the gradient method can finish. When both stall the ridge is real, not a
    tuning problem, and the caller is told rather than the warning being buried.
    """
    results = model.fit(disp=False, maxiter=MAX_ITER)
    if results.mle_retvals.get("converged", True):
        return results

    log.info("%s stalled under L-BFGS; retrying from a Nelder-Mead warm start", label)
    try:
        seed = model.fit(method="nm", maxiter=800, disp=False)
        warm = model.fit(start_params=seed.params, disp=False, maxiter=MAX_ITER)
    except Exception as exc:  # noqa: BLE001 - keep the first fit rather than nothing
        log.warning("%s warm start failed (%s); keeping the L-BFGS fit", label, exc)
        return results

    if warm.mle_retvals.get("converged", True):
        log.info("%s converged after the warm start", label)
        return warm

    # Neither converged. Keep whichever fits better and say so.
    better = warm if warm.aic < results.aic else results
    log.warning(
        "%s did not converge from either start. The regressors are close to "
        "collinear, so the likelihood has a ridge rather than a peak; "
        "coefficients are indicative and the drivers panel should be read as such.",
        label,
    )
    return better


def fit(frame: pd.DataFrame, vessel_class: str, order: tuple[int, int, int] = DEFAULT_ORDER) -> ProjectionBundle:
    """Estimate one model. Called by train.py, never by a request handler."""
    from statsmodels.tsa.statespace.sarimax import SARIMAX  # noqa: PLC0415

    features = exog_features_for(vessel_class)
    exog_mean = frame[features].mean()
    exog_std = frame[features].std()
    exog = standardise(frame, features, exog_mean, exog_std)

    model = SARIMAX(
        frame["log_rate"],
        exog=exog,
        order=order,
        trend="c",
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    results = _fit_with_warm_start(model, vessel_class)
    converged = bool(results.mle_retvals.get("converged", True))

    return ProjectionBundle(
        vessel_class=vessel_class.lower(),
        order=order,
        features=list(features),
        results=results,
        trained_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        train_rows=int(len(frame)),
        train_end=frame.index[-1].date().isoformat(),
        aic=float(results.aic),
        exog_mean=exog_mean,
        exog_std=exog_std,
        converged=converged,
    )


# ── Forecasting ───────────────────────────────────────────────────────────────

def _apply_to_latest(bundle: ProjectionBundle, frame: pd.DataFrame):
    """Re-filter the trained model over the newest data without re-estimating."""
    expected = exog_features_for(bundle.vessel_class)
    if list(bundle.features) != expected:
        raise ValueError(
            f"pickle for {bundle.vessel_class} was trained on {bundle.features}, "
            f"code expects {expected}; retrain with train.py"
        )
    exog = _scaled_exog(bundle, frame, expected)
    return bundle.results.apply(frame["log_rate"], exog=exog, refit=False)


def _scaled_exog(bundle: ProjectionBundle, frame: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """Apply the training scaler, or pass through for a pre-scaler pickle."""
    if bundle.exog_mean is None or bundle.exog_std is None:
        return frame[features]
    return standardise(frame, features, bundle.exog_mean, bundle.exog_std)


def forecast(
    bundle: ProjectionBundle,
    frame: pd.DataFrame,
    horizons: tuple[int, ...] = HORIZONS,
    scenario: dict[str, float] | None = None,
) -> dict:
    """Forecast to the longest horizon, with 80% and 95% prediction intervals.

    Everything is estimated in log space and exponentiated on the way out, so
    the intervals are asymmetric in price terms, which is how freight actually
    behaves: a spike has more room above than a slump has below.
    """
    steps = max(horizons)
    results = _apply_to_latest(bundle, frame)
    raw_exog = future_exog(frame, steps, scenario, features=list(bundle.features))
    exog = _scaled_exog(bundle, raw_exog, list(bundle.features))

    prediction = results.get_forecast(steps=steps, exog=exog)
    mean_log = prediction.predicted_mean
    ci80 = prediction.conf_int(alpha=0.20)
    ci95 = prediction.conf_int(alpha=0.05)

    dates = [d.date().isoformat() for d in exog.index]
    point = np.exp(mean_log.to_numpy(dtype=float))

    def band(ci: pd.DataFrame) -> list[dict]:
        lower = np.exp(ci.iloc[:, 0].to_numpy(dtype=float))
        upper = np.exp(ci.iloc[:, 1].to_numpy(dtype=float))
        return [
            {"date": d, "lower": round(float(lo), 3), "upper": round(float(hi), 3)}
            for d, lo, hi in zip(dates, lower, upper)
        ]

    return {
        "forecast": [
            {"date": d, "value": round(float(v), 3)} for d, v in zip(dates, point)
        ],
        "intervals": {"p80": band(ci80), "p95": band(ci95)},
        "horizon_points": {
            str(h): {
                "date": dates[h - 1],
                "value": round(float(point[h - 1]), 3),
                "p80": [
                    round(float(np.exp(ci80.iloc[h - 1, 0])), 3),
                    round(float(np.exp(ci80.iloc[h - 1, 1])), 3),
                ],
                "p95": [
                    round(float(np.exp(ci95.iloc[h - 1, 0])), 3),
                    round(float(np.exp(ci95.iloc[h - 1, 1])), 3),
                ],
            }
            for h in horizons
            if h <= steps
        },
        "_results": results,
        "_exog": exog,
        "_point": point,
    }


def driver_contributions(
    bundle: ProjectionBundle,
    frame: pd.DataFrame,
    exog: pd.DataFrame,
    level_usd: float,
    horizon: int = 90,
) -> list[dict]:
    """What each regressor is worth, in dollars per tonne, at one horizon.

    Contribution is the coefficient times the regressor's distance from its
    training mean, converted out of log space against the forecast level. It
    answers "how much of this number is the fuel price" rather than reporting a
    bare coefficient nobody can act on.
    """
    results = bundle.results
    params = results.params
    # `exog` arrives standardised, so each value is already the regressor's
    # distance from its training mean, in standard deviations.
    row = exog.iloc[min(horizon, len(exog)) - 1]
    scaled = bundle.exog_mean is not None

    drivers: list[dict] = []
    seasonal_log = 0.0
    for name in list(bundle.features):
        if name not in params.index:
            continue
        coefficient = float(params[name])
        centred = float(row[name]) if scaled else float(row[name] - frame[name].mean())
        log_effect = coefficient * centred

        if name.startswith("month_"):
            # The two Fourier terms are one idea; report them together.
            seasonal_log += log_effect
            continue

        drivers.append(
            {
                "feature": FEATURE_LABELS.get(name, name),
                "key": name,
                "coefficient": round(coefficient, 5),
                "contribution": round(float(level_usd * (np.exp(log_effect) - 1.0)), 3),
            }
        )

    drivers.append(
        {
            "feature": "Annual seasonality",
            "key": "seasonality",
            "coefficient": None,
            "contribution": round(float(level_usd * (np.exp(seasonal_log) - 1.0)), 3),
        }
    )

    drivers.sort(key=lambda d: abs(d["contribution"]), reverse=True)
    return drivers


# ── Backtesting ───────────────────────────────────────────────────────────────

def _mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    mask = np.abs(actual) > 1e-9
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100.0)


def _rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.sqrt(np.mean((actual - predicted) ** 2)))


def rolling_origin_backtest(
    frame: pd.DataFrame,
    horizons: tuple[int, ...] = HORIZONS,
    folds: int = 4,
    order: tuple[int, int, int] = DEFAULT_ORDER,
    min_train: int = 365,
    vessel_class: str | None = None,
) -> dict:
    """Walk the origin forward and score each horizon out of sample.

    At every origin the model is refitted on data up to that point only, then
    asked for the next 180 days. Nothing after the origin touches the fit, so
    the scores are honest rather than in-sample flattery.
    """
    from statsmodels.tsa.statespace.sarimax import SARIMAX  # noqa: PLC0415

    features = exog_features_for(vessel_class or frame.attrs.get("vessel_class", ""))
    longest = max(horizons)
    usable = len(frame) - longest
    if usable <= min_train:
        raise ValueError(f"need more than {min_train + longest} rows to backtest; have {len(frame)}")

    step = max(1, (usable - min_train) // folds)
    origins = [min_train + step * i for i in range(folds) if min_train + step * i + longest <= len(frame)]
    if not origins:
        raise ValueError("no valid backtest origins")

    errors: dict[int, list[tuple[float, float]]] = {h: [] for h in horizons}

    for origin in origins:
        train = frame.iloc[:origin]
        future = frame.iloc[origin : origin + longest]
        try:
            # Scale on the training window only. Using the whole series would
            # leak the test period's level into the fit.
            fold_mean = train[features].mean()
            fold_std = train[features].std()
            fitted = SARIMAX(
                train["log_rate"],
                exog=standardise(train, features, fold_mean, fold_std),
                order=order,
                trend="c",
                enforce_stationarity=False,
                enforce_invertibility=False,
            ).fit(disp=False, maxiter=MAX_ITER)
            # Regressors are known over the test window, so the score measures
            # the rate model, not our ability to forecast fuel prices.
            predicted = np.exp(
                fitted.get_forecast(
                    steps=longest,
                    exog=standardise(future, features, fold_mean, fold_std),
                ).predicted_mean.to_numpy(dtype=float)
            )
        except Exception as exc:  # noqa: BLE001 - a bad fold must not lose the others
            log.warning("backtest fold at origin %s failed: %s", origin, exc)
            continue

        actual = future["rate"].to_numpy(dtype=float)
        for h in horizons:
            if h <= len(actual):
                errors[h].append((actual[h - 1], predicted[h - 1]))

    out: dict[str, dict] = {}
    for h in horizons:
        pairs = errors[h]
        if not pairs:
            out[str(h)] = {"mape": None, "rmse": None, "folds": 0}
            continue
        actual = np.array([a for a, _ in pairs])
        predicted = np.array([p for _, p in pairs])
        out[str(h)] = {
            "mape": round(_mape(actual, predicted), 3),
            "rmse": round(_rmse(actual, predicted), 4),
            "folds": len(pairs),
        }
    return out


# ── Metrics file ──────────────────────────────────────────────────────────────

def write_metrics(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def read_metrics(path: Path) -> dict:
    """Never raises. A missing or corrupt metrics file must not stop the API."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        log.warning("no usable metrics at %s: %s", path, exc)
        return {}
