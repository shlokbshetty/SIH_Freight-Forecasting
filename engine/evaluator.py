"""
ML Model Evaluation & Visualization Engine.

Computes diagnostic metrics (MAE, RMSE, MAPE, R², Pinball Loss) for the
Multi-Quantile LightGBM freight forecaster and generates four publication-ready
diagnostic plots saved to reports/plots/.

All matplotlib rendering uses the Agg non-interactive backend, making this safe
for headless / CI environments with no display server.
"""

import os
import warnings
import numpy as np
import pandas as pd

# --- Headless backend BEFORE any other matplotlib import ---
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

warnings.filterwarnings("ignore", category=UserWarning)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(BASE_DIR, "reports", "plots")

# ── Design constants ─────────────────────────────────────────────────────────
PALETTE = {
    "bg": "#0D1117",
    "panel": "#161B22",
    "border": "#30363D",
    "p10": "#3FB950",       # green
    "p50": "#F0C132",       # amber
    "p90": "#F85149",       # red
    "actual": "#58A6FF",    # blue
    "residual": "#BC8CFF",  # violet
    "neutral": "#8B949E",
}

sns.set_theme(style="dark", rc={
    "axes.facecolor": PALETTE["panel"],
    "figure.facecolor": PALETTE["bg"],
    "axes.edgecolor": PALETTE["border"],
    "axes.labelcolor": "#E6EDF3",
    "text.color": "#E6EDF3",
    "xtick.color": "#8B949E",
    "ytick.color": "#8B949E",
    "grid.color": "#21262D",
    "grid.linestyle": "--",
    "grid.alpha": 0.6,
    "font.family": "DejaVu Sans",
})


# ═══════════════════════════════════════════════════════════════════════════════
# 1.  METRICS ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def _pinball_loss(y_true: np.ndarray, y_pred: np.ndarray, alpha: float) -> float:
    """Computes the Pinball / Quantile loss for a single alpha level."""
    delta = y_true - y_pred
    loss = np.where(delta >= 0, alpha * delta, (alpha - 1.0) * delta)
    return float(np.mean(loss))


def _mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Percentage Error, guarded against zero actuals."""
    mask = y_true != 0.0
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100.0)


def compute_evaluation_metrics(
    y_true: np.ndarray,
    y_p10: np.ndarray,
    y_p50: np.ndarray,
    y_p90: np.ndarray,
) -> dict:
    """
    Returns a flat metrics dictionary for the full quantile suite.

    Keys
    ----
    mae, rmse, mape, r2                   — Point-forecast accuracy (p50)
    pinball_p10, pinball_p50, pinball_p90 — Quantile calibration losses
    coverage_80pct                         — Empirical 80 % PI coverage rate
    """
    y_true = np.asarray(y_true, dtype=float)
    y_p10 = np.asarray(y_p10, dtype=float)
    y_p50 = np.asarray(y_p50, dtype=float)
    y_p90 = np.asarray(y_p90, dtype=float)

    mae_val = float(mean_absolute_error(y_true, y_p50))
    rmse_val = float(np.sqrt(mean_squared_error(y_true, y_p50)))
    mape_val = _mape(y_true, y_p50)
    r2_val = float(r2_score(y_true, y_p50))

    pb_p10 = _pinball_loss(y_true, y_p10, 0.10)
    pb_p50 = _pinball_loss(y_true, y_p50, 0.50)
    pb_p90 = _pinball_loss(y_true, y_p90, 0.90)

    # Empirical 80 % coverage (actuals between p10 and p90)
    in_band = np.sum((y_true >= y_p10) & (y_true <= y_p90))
    coverage = float(in_band / len(y_true)) * 100.0

    return {
        "mae": round(mae_val, 4),
        "rmse": round(rmse_val, 4),
        "mape_pct": round(mape_val, 2),
        "r2": round(r2_val, 4),
        "pinball_p10": round(pb_p10, 4),
        "pinball_p50": round(pb_p50, 4),
        "pinball_p90": round(pb_p90, 4),
        "coverage_80pct": round(coverage, 1),
    }


def print_metrics_report(metrics: dict, route_code: str = "") -> None:
    """Pretty-prints a formatted metrics table to stdout."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich import box as rbox

        console = Console()
        tbl = Table(
            title=f"[bold]Model Evaluation Metrics — {route_code}[/bold]",
            box=rbox.ROUNDED,
            header_style="bold magenta",
        )
        tbl.add_column("Metric", style="cyan", width=28)
        tbl.add_column("Value", justify="right", style="bold yellow", width=14)
        tbl.add_column("Description", style="dim white")

        rows = [
            ("MAE (p50)", f"{metrics['mae']:.4f} $/T", "Mean Absolute Error on median forecast"),
            ("RMSE (p50)", f"{metrics['rmse']:.4f} $/T", "Root Mean Squared Error"),
            ("MAPE (p50)", f"{metrics['mape_pct']:.2f} %", "Mean Absolute Percentage Error"),
            ("R² Score (p50)", f"{metrics['r2']:.4f}", "Coefficient of determination (1.0 = perfect)"),
            ("Pinball Loss p10", f"{metrics['pinball_p10']:.4f}", "Quantile calibration loss at α=0.10"),
            ("Pinball Loss p50", f"{metrics['pinball_p50']:.4f}", "Quantile calibration loss at α=0.50"),
            ("Pinball Loss p90", f"{metrics['pinball_p90']:.4f}", "Quantile calibration loss at α=0.90"),
            ("80% PI Coverage", f"{metrics['coverage_80pct']:.1f} %", "% actuals inside [p10, p90] band (target: 80%)"),
        ]
        for name, val, desc in rows:
            tbl.add_row(name, val, desc)

        console.print(tbl)
    except ImportError:
        # Fallback plain print
        print(f"\n{'─'*60}")
        print(f"  Model Evaluation Metrics — {route_code}")
        print(f"{'─'*60}")
        for k, v in metrics.items():
            print(f"  {k:<25} {v}")
        print(f"{'─'*60}\n")


# ═══════════════════════════════════════════════════════════════════════════════
# 2.  PLOT GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

def _save_figure(fig: plt.Figure, filename: str) -> str:
    """Saves figure to reports/plots/ and returns the absolute path."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    path = os.path.join(REPORTS_DIR, filename)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=PALETTE["bg"])
    plt.close(fig)
    return path


def plot_forecast_confidence_bands(
    dates: list,
    y_actual: np.ndarray,
    y_p10: np.ndarray,
    y_p50: np.ndarray,
    y_p90: np.ndarray,
    route_code: str = "Route",
) -> str:
    """
    Time-series confidence band chart overlaying actuals with p10/p50/p90 quantiles.
    Saved as: reports/plots/forecast_confidence_bands.png
    """
    fig, ax = plt.subplots(figsize=(14, 6))

    x = np.arange(len(dates))

    # Confidence fill
    ax.fill_between(x, y_p10, y_p90, alpha=0.18, color=PALETTE["p50"],
                    label="80% Confidence Band (p10–p90)")
    ax.fill_between(x, y_p10, y_p50, alpha=0.12, color=PALETTE["p10"])

    # Quantile lines
    ax.plot(x, y_p10, color=PALETTE["p10"], linewidth=1.2, linestyle="--",
            label="p10 Bearish Low", alpha=0.85)
    ax.plot(x, y_p90, color=PALETTE["p90"], linewidth=1.2, linestyle="--",
            label="p90 Bullish High", alpha=0.85)
    ax.plot(x, y_p50, color=PALETTE["p50"], linewidth=2.0,
            label="p50 Median Forecast", zorder=5)
    ax.scatter(x, y_actual, color=PALETTE["actual"], s=22, zorder=6,
               label="Actual Rate", edgecolors="white", linewidths=0.3)

    # Axis labels
    tick_step = max(1, len(dates) // 12)
    ax.set_xticks(x[::tick_step])
    ax.set_xticklabels(
        [str(d)[:7] for d in dates[::tick_step]],
        rotation=30, ha="right", fontsize=8
    )
    ax.set_ylabel("Freight Rate (USD / MT)", fontsize=10)
    ax.set_title(
        f"Multi-Quantile LightGBM Forecast Confidence Bands — {route_code}",
        fontsize=12, fontweight="bold", pad=14
    )
    ax.legend(loc="upper left", fontsize=8, framealpha=0.25)
    ax.grid(True, alpha=0.4)
    fig.tight_layout()

    return _save_figure(fig, "forecast_confidence_bands.png")


def plot_feature_importance(
    feature_names: list,
    importances: np.ndarray,
    route_code: str = "Route",
    top_n: int = 20,
) -> str:
    """
    Horizontal bar chart of the top-N LightGBM feature importances (gain).
    Saved as: reports/plots/feature_importance.png
    """
    pairs = sorted(zip(importances, feature_names), reverse=True)[:top_n]
    imp_vals = np.array([p[0] for p in pairs])
    imp_names = [p[1] for p in pairs]

    # Normalize to 0–100
    if imp_vals.max() > 0:
        imp_vals = imp_vals / imp_vals.max() * 100.0

    fig, ax = plt.subplots(figsize=(10, 7))

    colors = plt.cm.RdYlGn(np.linspace(0.25, 0.85, len(imp_vals)))[::-1]
    bars = ax.barh(range(len(imp_names)), imp_vals[::-1], color=colors[::-1],
                   edgecolor=PALETTE["border"], linewidth=0.6)

    ax.set_yticks(range(len(imp_names)))
    ax.set_yticklabels(imp_names[::-1], fontsize=8)
    ax.set_xlabel("Relative Importance (Gain, normalized to 100)", fontsize=9)
    ax.set_title(
        f"Top-{top_n} Feature Importances (p50 Model) — {route_code}",
        fontsize=11, fontweight="bold", pad=12
    )

    # Value labels
    for bar, val in zip(bars, imp_vals[::-1]):
        ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}", va="center", ha="left", fontsize=7,
                color=PALETTE["neutral"])

    ax.grid(axis="x", alpha=0.4)
    fig.tight_layout()

    return _save_figure(fig, "feature_importance.png")


def plot_breakeven_cdf(
    mean_spot_rate: float,
    volatility_std: float,
    breakeven_rate: float,
    route_code: str = "Route",
) -> str:
    """
    CDF of the inferred spot rate distribution with break-even annotation.
    Saved as: reports/plots/break_even_cdf.png
    """
    from scipy.stats import norm

    x = np.linspace(
        mean_spot_rate - 4 * volatility_std,
        mean_spot_rate + 4 * volatility_std,
        400
    )
    pdf = norm.pdf(x, loc=mean_spot_rate, scale=volatility_std)
    cdf = norm.cdf(x, loc=mean_spot_rate, scale=volatility_std)
    prob_below = float(norm.cdf(breakeven_rate, loc=mean_spot_rate, scale=volatility_std))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # ── Left: PDF with shaded tail ──────────────────────────────────────────
    ax1.plot(x, pdf, color=PALETTE["p50"], linewidth=2.0)
    ax1.fill_between(x, pdf, where=(x <= breakeven_rate),
                     alpha=0.35, color=PALETTE["p10"],
                     label=f"P(Spot ≤ Break-Even) = {prob_below*100:.1f}%")
    ax1.axvline(breakeven_rate, color=PALETTE["p90"], linewidth=1.8, linestyle="--",
                label=f"Break-Even ${breakeven_rate:.2f}/T")
    ax1.axvline(mean_spot_rate, color=PALETTE["p50"], linewidth=1.4, linestyle=":",
                label=f"Mean Spot ${mean_spot_rate:.2f}/T")
    ax1.set_xlabel("Spot Freight Rate (USD / MT)", fontsize=9)
    ax1.set_ylabel("Probability Density", fontsize=9)
    ax1.set_title("Inferred Spot Rate PDF (Gaussian from Quantile Spread)", fontsize=10, fontweight="bold")
    ax1.legend(fontsize=8, framealpha=0.3)
    ax1.grid(True, alpha=0.35)

    # ── Right: CDF ──────────────────────────────────────────────────────────
    ax2.plot(x, cdf * 100.0, color=PALETTE["actual"], linewidth=2.0)
    ax2.axhline(prob_below * 100.0, color=PALETTE["p10"], linewidth=1.2, linestyle="--",
                label=f"P(below break-even) = {prob_below*100:.1f}%")
    ax2.axvline(breakeven_rate, color=PALETTE["p90"], linewidth=1.8, linestyle="--",
                label=f"Break-Even ${breakeven_rate:.2f}/T")
    ax2.scatter([breakeven_rate], [prob_below * 100.0],
                color="white", s=60, zorder=5, edgecolors=PALETTE["p90"])
    ax2.set_xlabel("Spot Freight Rate (USD / MT)", fontsize=9)
    ax2.set_ylabel("Cumulative Probability (%)", fontsize=9)
    ax2.set_title("Spot Rate CDF — Break-Even Risk Threshold", fontsize=10, fontweight="bold")
    ax2.legend(fontsize=8, framealpha=0.3)
    ax2.grid(True, alpha=0.35)

    fig.suptitle(
        f"Break-Even Probability Analysis — {route_code}",
        fontsize=12, fontweight="bold", y=1.01
    )
    fig.tight_layout()

    return _save_figure(fig, "break_even_cdf.png")


def plot_residual_distribution(
    y_true: np.ndarray,
    y_p50: np.ndarray,
    route_code: str = "Route",
) -> str:
    """
    Residual (actual − p50) distribution: histogram with KDE overlay and Q-Q plot.
    Saved as: reports/plots/residual_distribution.png
    """
    from scipy import stats

    residuals = np.asarray(y_true, dtype=float) - np.asarray(y_p50, dtype=float)

    fig = plt.figure(figsize=(14, 5))
    gs = gridspec.GridSpec(1, 2, width_ratios=[1.6, 1])

    # ── Histogram + KDE ────────────────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0])
    ax1.hist(residuals, bins=25, color=PALETTE["residual"], alpha=0.5,
             edgecolor=PALETTE["border"], linewidth=0.5, density=True)
    kde_x = np.linspace(residuals.min(), residuals.max(), 300)
    kde_vals = stats.gaussian_kde(residuals)(kde_x)
    ax1.plot(kde_x, kde_vals, color=PALETTE["p50"], linewidth=2.0, label="KDE")
    ax1.axvline(0.0, color=PALETTE["actual"], linewidth=1.5, linestyle="--", label="Zero (ideal)")
    ax1.set_xlabel("Residual (Actual − p50 Forecast) USD/T", fontsize=9)
    ax1.set_ylabel("Density", fontsize=9)
    ax1.set_title("p50 Residual Distribution", fontsize=10, fontweight="bold")
    ax1.legend(fontsize=8, framealpha=0.3)
    ax1.grid(True, alpha=0.35)

    # Annotation: mean and std
    ax1.text(0.97, 0.95,
             f"μ = {residuals.mean():.3f}\nσ = {residuals.std():.3f}\nN = {len(residuals)}",
             transform=ax1.transAxes, ha="right", va="top",
             fontsize=8, color=PALETTE["neutral"],
             bbox=dict(boxstyle="round,pad=0.3", facecolor=PALETTE["panel"], alpha=0.7))

    # ── Q-Q Plot ────────────────────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[1])
    (qq_x, qq_y), (slope, intercept, _) = stats.probplot(residuals, dist="norm")
    ax2.scatter(qq_x, qq_y, color=PALETTE["residual"], s=20, alpha=0.7, label="Quantiles")
    fit_line = slope * np.array(qq_x) + intercept
    ax2.plot(qq_x, fit_line, color=PALETTE["p50"], linewidth=1.8, linestyle="--",
             label="Normal Fit")
    ax2.set_xlabel("Theoretical Quantiles", fontsize=9)
    ax2.set_ylabel("Sample Quantiles", fontsize=9)
    ax2.set_title("Q-Q Plot (Normality Check)", fontsize=10, fontweight="bold")
    ax2.legend(fontsize=8, framealpha=0.3)
    ax2.grid(True, alpha=0.35)

    fig.suptitle(
        f"p50 Forecast Residual Diagnostics — {route_code}",
        fontsize=12, fontweight="bold", y=1.02
    )
    fig.tight_layout()

    return _save_figure(fig, "residual_distribution.png")


# ═══════════════════════════════════════════════════════════════════════════════
# 3.  TOP-LEVEL ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

def run_full_evaluation(route_code: str = "NEWCASTLE_HALDIA_PANAMAX") -> dict:
    """
    End-to-end evaluation orchestrator:
      1. Loads training data via FreightFeatureEngineer
      2. Trains (or reloads) Multi-Quantile LightGBM models
      3. Runs in-sample prediction for diagnostics
      4. Computes all metrics
      5. Generates and saves all four diagnostic plots
      6. Prints metrics table to stdout
      7. Returns a result dict with metric values and plot file paths

    Parameters
    ----------
    route_code : str
        Parquet route column identifier, e.g. 'NEWCASTLE_HALDIA_PANAMAX'

    Returns
    -------
    dict with keys:
        route_code, metrics, plot_paths (list of absolute paths)
    """
    from data.features import FreightFeatureEngineer
    from engine.ml_forecaster import MultiQuantileForecaster

    # ── Load & engineer features ────────────────────────────────────────────
    fe = FreightFeatureEngineer()
    X, y = fe.build_training_dataset(route_code)
    dates = list(X.index if isinstance(X.index, pd.DatetimeIndex) else range(len(X)))

    # ── Train / reload models ───────────────────────────────────────────────
    forecaster = MultiQuantileForecaster(feature_engineer=fe)
    models = forecaster.get_or_train_route_models(route_code)

    # ── In-sample predictions ───────────────────────────────────────────────
    raw_p10 = models["p10"].predict(X)
    raw_p50 = models["p50"].predict(X)
    raw_p90 = models["p90"].predict(X)

    y_arr = np.asarray(y, dtype=float)

    # Enforce monotonicity row-wise
    y_p10 = np.minimum(raw_p10, raw_p50)
    y_p90 = np.maximum(raw_p50, raw_p90)
    y_p50 = raw_p50.copy()

    # ── Metrics ─────────────────────────────────────────────────────────────
    metrics = compute_evaluation_metrics(y_arr, y_p10, y_p50, y_p90)
    print_metrics_report(metrics, route_code)

    # ── Feature importance (from p50 model) ─────────────────────────────────
    model_p50 = models["p50"]
    feature_names = list(X.columns)
    importances = model_p50.feature_importances_

    # ── Break-even parameters (use Scenario B defaults for illustration) ────
    mean_spot = float(np.mean(y_p50))
    span_mean = float(np.mean(y_p90 - y_p10))
    sigma = max(0.50, span_mean / 2.563)
    breakeven_rate = round(mean_spot * 0.88, 2)   # ~12 % below mean (illustrative)

    # ── Generate all four plots ──────────────────────────────────────────────
    plot_paths = []

    p1 = plot_forecast_confidence_bands(dates, y_arr, y_p10, y_p50, y_p90, route_code)
    plot_paths.append(p1)

    p2 = plot_feature_importance(feature_names, importances, route_code)
    plot_paths.append(p2)

    p3 = plot_breakeven_cdf(mean_spot, sigma, breakeven_rate, route_code)
    plot_paths.append(p3)

    p4 = plot_residual_distribution(y_arr, y_p50, route_code)
    plot_paths.append(p4)

    return {
        "route_code": route_code,
        "metrics": metrics,
        "plot_paths": plot_paths,
    }
