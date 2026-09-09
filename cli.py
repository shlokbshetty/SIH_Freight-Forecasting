#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ministry of Ports, Shipping and Waterways (MoPSW)
Intelligent Freight Procurement & Vessel Feasibility Decision Support Platform.

CLI Interface & Interactive Demonstration Tool.
"""

import sys
import os
import argparse
from typing import Optional

# Ensure UTF-8 output on Windows consoles if possible
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from rich.align import Align

from data.ports import get_port, Port, get_all_ports
from data.vessels import get_vessel_class, VesselClass
from data.mock_rates import MockRateProvider, OperationalCosts
from engine.feasibility import FeasibilityEngine, VesselFeasibilityResult
from engine.financial_evaluator import FinancialEvaluator, EvaluationResult


console = Console(width=max(Console().width or 120, 115))


def print_banner():
    """Renders the executive government & maritime platform banner."""
    title_text = Text()
    title_text.append("MINISTRY OF PORTS, SHIPPING AND WATERWAYS\n", style="bold cyan")
    title_text.append("GOVERNMENT OF INDIA | SAGARMANTHAN DECISION SUPPORT SYSTEM\n", style="bold white")
    title_text.append("Bulk Cargo Vessel Feasibility, Sagar/Sandheads Router & Financial Evaluator", style="italic yellow")

    banner_panel = Panel(
        Align.center(title_text),
        box=box.DOUBLE_EDGE,
        border_style="bright_blue",
        padding=(1, 2),
    )
    console.print(banner_panel)


def render_ports_table(origin: Port, destination: Port):
    """Renders port infrastructure parameters and dimensional constraints."""
    table = Table(
        title="[bold]Port Infrastructure & Berthing Capacity[/bold]",
        box=box.ROUNDED,
        header_style="bold magenta",
        expand=True,
    )
    table.add_column("Call Type", style="cyan", width=12)
    table.add_column("Port Name", style="bold white", width=28)
    table.add_column("Country", style="green", width=14)
    table.add_column("Max Draft", justify="right", style="bright_yellow", width=11)
    table.add_column("Max LOA", justify="right", style="bright_yellow", width=11)
    table.add_column("Max Beam", justify="right", style="bright_yellow", width=10)
    table.add_column("Handling Rate", justify="right", style="cyan", width=14)
    table.add_column("Operational Notes", style="dim white")

    # Origin
    table.add_row(
        "ORIGIN (Load)",
        origin.name,
        origin.country,
        f"{origin.max_draft:.1f} m",
        "Unlimited" if origin.max_loa == float("inf") else f"{origin.max_loa:.1f} m",
        "Unlimited" if origin.max_beam == float("inf") else f"{origin.max_beam:.1f} m",
        f"{origin.load_rate:,.0f} TPD",
        origin.notes,
    )

    # Destination
    table.add_row(
        "DEST (Disch)",
        destination.name,
        destination.country,
        f"{destination.max_draft:.1f} m",
        "Unlimited" if destination.max_loa == float("inf") else f"{destination.max_loa:.1f} m",
        "Unlimited" if destination.max_beam == float("inf") else f"{destination.max_beam:.1f} m",
        f"{destination.discharge_rate:,.0f} TPD",
        destination.notes,
    )

    console.print(table)


def render_feasibility_table(
    ranked_results: list[VesselFeasibilityResult], cargo_tonnage: float
):
    """Renders the vessel feasibility evaluation matrix."""
    table = Table(
        title=f"[bold]Dry Bulk Fleet Feasibility & Dimensional Screening (Cargo: {cargo_tonnage:,.0f} MT)[/bold]",
        box=box.ROUNDED,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Rank", justify="center", style="bold yellow", width=6)
    table.add_column("Vessel Class", style="bold white", width=22)
    table.add_column("DWT Range", justify="center", style="dim", width=19)
    table.add_column("Oper. Draft", justify="right", style="bright_yellow", width=13)
    table.add_column("Feasibility", justify="center", width=13)
    table.add_column("Berthing Mode", justify="center", width=18)
    table.add_column("Draft Clr", justify="right", width=11)
    table.add_column("LOA Clr", justify="right", width=10)
    table.add_column("Suitability", justify="right", style="bold green", width=13)

    for i, res in enumerate(ranked_results, start=1):
        v = res.vessel_class
        operating_draft = v.draft_at_tonnage(cargo_tonnage)

        # Status badge
        if res.is_feasible:
            status_badge = "[bold black on green] FEASIBLE [/bold black on green]"
        else:
            status_badge = "[bold white on red] REJECTED [/bold white on red]"

        # Berthing mode badge
        if not res.is_feasible:
            berth_mode = "[dim]N/A (Exceeded)[/dim]"
        elif res.is_direct_berth:
            berth_mode = "[bold green]DIRECT BERTH[/bold green]"
        else:
            berth_mode = "[bold black on yellow] SAGAR STS [/bold black on yellow]"

        # Clearance margins at destination
        dest_draft_check = next((c for c in res.destination_checks if c.dimension_name == "Draft"), None)
        dest_loa_check = next((c for c in res.destination_checks if c.dimension_name == "LOA"), None)

        d_clr_str = f"{dest_draft_check.clearance_margin:+.1f}m" if dest_draft_check else "-"
        loa_clr_str = f"{dest_loa_check.clearance_margin:+.1f}m" if dest_loa_check else "-"

        # Colorize clearances
        if dest_draft_check and dest_draft_check.clearance_margin < 0:
            d_clr_str = f"[bold red]{d_clr_str}[/bold red]"
        else:
            d_clr_str = f"[green]{d_clr_str}[/green]"

        if dest_loa_check and dest_loa_check.clearance_margin < 0:
            loa_clr_str = f"[bold red]{loa_clr_str}[/bold red]"
        else:
            loa_clr_str = f"[green]{loa_clr_str}[/green]"

        table.add_row(
            f"#{i}",
            v.name,
            v.capacity_range_str,
            f"{operating_draft:.2f} m",
            status_badge,
            berth_mode,
            d_clr_str,
            loa_clr_str,
            f"{res.suitability_score:.1f} / 100",
        )

    console.print(table)


def render_lighterage_alert(result: VesselFeasibilityResult):
    """Renders specialized alert box when Sagar/Sandheads lighterage is triggered."""
    plan = result.lighterage_plan
    if not plan.is_required:
        return

    alert_text = Text()
    alert_text.append(f"{plan.warning_message}\n\n", style="bold red")
    alert_text.append("• Deepwater Anchorage: ", style="bold white")
    alert_text.append(f"{plan.location}\n", style="yellow")
    alert_text.append("• Excess Draft at Dock: ", style="bold white")
    alert_text.append(f"+{plan.excess_draft:.2f} m above maximum permissible dock draft\n", style="bright_red")
    alert_text.append("• Mandatory Transshipment Cargo: ", style="bold white")
    alert_text.append(f"{plan.lightered_tonnage:,.0f} MT lightered to daughter barges ({plan.retained_tonnage:,.0f} MT enters dock)\n", style="cyan")
    alert_text.append("• Lighterage Tariff: ", style="bold white")
    alert_text.append(f"${plan.lighterage_rate:.2f}/MT (${plan.lighterage_cost:,.2f} per voyage call)\n", style="yellow")
    alert_text.append("• Operational Turnaround Penalty: ", style="bold white")
    alert_text.append(f"+{plan.time_penalty_days:.1f} days (Anchorage STS transfer and barge clearance)", style="bright_magenta")

    panel = Panel(
        alert_text,
        title="[bold red]⚠️ MARITIME ROUTING ALERT: TRANSSHIPMENT REQUIRED[/bold red]",
        border_style="red",
        box=box.DOUBLE_EDGE,
        padding=(1, 2),
    )
    console.print(panel)


def render_financial_table(eval_result: EvaluationResult):
    """Renders the voyage-by-voyage cost breakdown table."""
    table = Table(
        title=f"[bold]Voyage-by-Voyage Spot vs. CVC Cost Evaluation ({eval_result.vessel_class.name} | {eval_result.cargo_tonnage:,.0f} MT)[/bold]",
        box=box.ROUNDED,
        header_style="bold green",
        expand=True,
    )
    table.add_column("Voyage", justify="center", style="cyan", width=8)
    table.add_column("Spot $/T", justify="right", style="bright_yellow", width=10)
    table.add_column("Spot Total", justify="right", style="yellow", width=13)
    table.add_column("CVC $/T", justify="right", style="bright_cyan", width=10)
    table.add_column("CVC Total", justify="right", style="cyan", width=13)
    table.add_column("Bunker", justify="right", style="dim", width=10)
    table.add_column("Port Dues", justify="right", style="dim", width=10)
    table.add_column("Demurrage", justify="right", style="dim", width=11)
    table.add_column("Lighterage", justify="right", style="dim", width=12)
    table.add_column("Net Savings", justify="right", style="bold green", width=13)

    for v in eval_result.voyages:
        savings_color = "bold green" if v.voyage_savings >= 0 else "bold red"
        table.add_row(
            f"Voyage {v.voyage_number}",
            f"${v.spot_freight_rate:.2f}",
            f"${v.spot_voyage_total:,.0f}",
            f"${v.cvc_freight_rate:.2f}",
            f"${v.cvc_voyage_total:,.0f}",
            f"${v.bunker_adj_cost:,.0f}",
            f"${v.port_charges:,.0f}",
            f"${v.demurrage_cost:,.0f}",
            f"${v.lighterage_cost:,.0f}" if v.lighterage_cost > 0 else "-",
            f"[{savings_color}]${v.voyage_savings:+,.0f}[/{savings_color}]",
        )

    # Totals Row
    table.add_section()
    table.add_row(
        "[bold]TOTALS[/bold]",
        f"[bold]${eval_result.average_spot_rate:.2f}[/bold]",
        f"[bold yellow]${eval_result.spot_total_usd:,.0f}[/bold yellow]",
        f"[bold]${eval_result.locked_cvc_rate:.2f}[/bold]",
        f"[bold cyan]${eval_result.cvc_total_usd:,.0f}[/bold cyan]",
        f"${sum(v.bunker_adj_cost for v in eval_result.voyages):,.0f}",
        f"${sum(v.port_charges for v in eval_result.voyages):,.0f}",
        f"${sum(v.demurrage_cost for v in eval_result.voyages):,.0f}",
        f"${sum(v.lighterage_cost for v in eval_result.voyages):,.0f}"
        if eval_result.lighterage_plan.is_required
        else "-",
        f"[bold green]${eval_result.base_case_delta_usd:+,.0f}[/bold green]",
    )

    console.print(table)


def render_ml_forecast_cone(eval_result: EvaluationResult):
    """Renders the Multi-Quantile LightGBM forecast confidence cone (p10, p50, p90)."""
    forecast = eval_result.ml_forecast
    if not forecast:
        return

    table = Table(
        title=f"[bold]Multi-Quantile ML Freight Forecast Cone ({forecast.route_code})[/bold]",
        box=box.ROUNDED,
        header_style="bold magenta",
        expand=True,
    )
    table.add_column("Voyage Horizon", justify="center", style="cyan", width=16)
    table.add_column("Bearish Low (p10)", justify="right", style="green", width=18)
    table.add_column("Median Forecast (p50)", justify="right", style="bold yellow", width=22)
    table.add_column("Bullish High (p90)", justify="right", style="bright_red", width=18)
    table.add_column("Volatility Spread", justify="right", style="dim", width=18)
    table.add_column("Forecast Model", style="dim white")

    for i in range(eval_result.num_voyages):
        p10 = forecast.p10_rates[i]
        p50 = forecast.p50_rates[i]
        p90 = forecast.p90_rates[i]
        spread = round(p90 - p10, 2)

        table.add_row(
            f"Voyage #{i + 1}",
            f"${p10:.2f} / MT",
            f"[bold yellow]${p50:.2f} / MT[/bold yellow]",
            f"${p90:.2f} / MT",
            f"±${spread / 2:.2f} (${spread:.2f} span)",
            "LightGBM Quantile (α=0.10, 0.50, 0.90)",
        )

    table.add_section()
    mean_p10 = sum(forecast.p10_rates) / len(forecast.p10_rates)
    mean_p50 = sum(forecast.p50_rates) / len(forecast.p50_rates)
    mean_p90 = sum(forecast.p90_rates) / len(forecast.p90_rates)
    table.add_row(
        "[bold]HORIZON MEAN[/bold]",
        f"[bold green]${mean_p10:.2f}[/bold green]",
        f"[bold yellow]${mean_p50:.2f}[/bold yellow]",
        f"[bold red]${mean_p90:.2f}[/bold red]",
        f"Implied σ = ${forecast.volatility_std:.2f}/T",
        "[bold cyan]Calibrated Asymmetric Band[/bold cyan]",
    )

    console.print(table)


def render_summary_cards(eval_result: EvaluationResult):
    """Renders high-level financial summary metrics and risk distribution cards."""
    # Financial Comparison Card
    summary_text = Text()
    summary_text.append("FINANCIAL COMPARISON SUMMARY (USD & INR)\n\n", style="bold white")
    summary_text.append("• Cumulative Spot Outlay: ", style="bold yellow")
    summary_text.append(f"${eval_result.spot_total_usd:,.0f} USD ", style="white")
    summary_text.append(f"(₹{eval_result.spot_total_inr / 1e7:,.2f} Cr)\n", style="dim yellow")

    if eval_result.p10_spot_total_usd > 0 and eval_result.p90_spot_total_usd > 0:
        summary_text.append("  (ML 80% Confidence Interval: ", style="dim")
        summary_text.append(f"${eval_result.p10_spot_total_usd:,.0f} [p10] to ${eval_result.p90_spot_total_usd:,.0f} [p90] USD)\n", style="cyan")

    summary_text.append("• Cumulative CVC Outlay:  ", style="bold cyan")
    summary_text.append(f"${eval_result.cvc_total_usd:,.0f} USD ", style="white")
    summary_text.append(f"(₹{eval_result.cvc_total_inr / 1e7:,.2f} Cr)\n", style="dim cyan")

    summary_text.append(f"• Base Case Contract Delta: ", style="bold green")
    delta_prefix = "Net Savings" if eval_result.is_cvc_favorable else "Net Deficit"
    summary_text.append(
        f"{delta_prefix} of ${abs(eval_result.base_case_delta_usd):,.0f} USD (₹{eval_result.base_case_delta_cr:.2f} Cr) @ ₹83.50/$1\n",
        style="bold green" if eval_result.is_cvc_favorable else "bold red",
    )
    summary_text.append(f"• Negotiated CVC Discount: ", style="bold white")
    summary_text.append(f"{eval_result.cvc_discount_pct:.1f}% below forecast average spot freight rate\n", style="cyan")

    panel_summary = Panel(
        summary_text,
        title="[bold cyan]Executive Financial Comparison[/bold cyan]",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )

    # Break-Even & Risk Forecast Card
    risk_text = Text()
    risk_text.append("BREAK-EVEN THRESHOLD & RISK PROBABILITY\n\n", style="bold white")
    risk_text.append(f"• Break-Even Spot Rate: ", style="bold yellow")
    risk_text.append(f"${eval_result.breakeven_spot_rate:.2f} / MT\n", style="bold yellow")
    risk_text.append("  (Market spot rate threshold where Spot and CVC equal out)\n\n", style="dim")

    risk_text.append(f"• Forecast Volatility Risk: ", style="bold magenta")
    risk_text.append(f"{eval_result.breakeven_probability_pct:.1f}%\n", style="bold magenta")
    risk_text.append(
        f"  (Probability that spot rate drops below ${eval_result.breakeven_spot_rate:.2f}/T over contract period)\n\n",
        style="dim",
    )

    risk_text.append("• Chartering Recommendation: ", style="bold white")
    if eval_result.is_cvc_favorable:
        risk_text.append(
            f"LOCK CVC CONTRACT. Low probability ({eval_result.breakeven_probability_pct:.0f}%) of spot falling below break-even.",
            style="bold green",
        )
    else:
        risk_text.append(
            "RETAIN SPOT FIXTURES. Spot market projected to be lower than fixed commitment.",
            style="bold yellow",
        )

    panel_risk = Panel(
        risk_text,
        title="[bold magenta]Break-Even & Market Probability[/bold magenta]",
        border_style="magenta",
        box=box.ROUNDED,
        padding=(1, 2),
    )

    console.print(panel_summary)
    console.print(panel_risk)


def render_headline_callout(eval_result: EvaluationResult):
    """Renders the exact dynamic headline summary callout box."""
    headline_text = Text(eval_result.headline_summary, style="bold white on blue")

    callout_panel = Panel(
        Align.center(headline_text),
        title="[bold yellow]★ EXECUTIVE DECISION HEADLINE ★[/bold yellow]",
        box=box.HEAVY,
        border_style="bright_yellow",
        padding=(1, 2),
    )
    console.print(callout_panel)


def execute_evaluation(
    cargo_tonnage: float,
    origin_name: str,
    destination_name: str,
    num_voyages: int = 4,
    cvc_discount_pct: float = 5.0,
    target_cvc_rate: Optional[float] = None,
    scenario_title: Optional[str] = None,
):
    """Orchestrates end-to-end feasibility and financial evaluation workflow."""
    if scenario_title:
        scenario_header = Text(f"\n▶ {scenario_title.upper()}", style="bold white on dark_green")
        console.print(Panel(Align.center(scenario_header), box=box.ROUNDED, border_style="green"))

    # 1. Resolve Ports
    try:
        origin = get_port(origin_name)
        destination = get_port(destination_name)
    except KeyError as e:
        console.print(f"[bold red]Error resolving port:[/bold red] {e}")
        return

    render_ports_table(origin, destination)

    # 2. Feasibility Engine Screening
    fe = FeasibilityEngine()
    ranked_vessels = fe.evaluate_route(cargo_tonnage, origin, destination)
    render_feasibility_table(ranked_vessels, cargo_tonnage)

    best_vessel_result = next((r for r in ranked_vessels if r.is_feasible), None)
    if not best_vessel_result:
        console.print("[bold red]CRITICAL: No registered vessel class is feasible for this route and cargo parcel.[/bold red]")
        return

    # 3. Sagar/Sandheads Lighterage Routing Alert
    render_lighterage_alert(best_vessel_result)

    # 4. Spot vs. CVC Financial Evaluation with ML Forecasting
    fin = FinancialEvaluator()
    eval_result = fin.evaluate(
        cargo_tonnage=cargo_tonnage,
        origin=origin,
        destination=destination,
        vessel=best_vessel_result.vessel_class,
        num_voyages=num_voyages,
        cvc_discount_pct=cvc_discount_pct,
        lighterage_plan=best_vessel_result.lighterage_plan,
        target_cvc_rate=target_cvc_rate,
        use_ml=True,
    )

    render_ml_forecast_cone(eval_result)
    render_financial_table(eval_result)
    render_summary_cards(eval_result)
    render_headline_callout(eval_result)


def run_demo_scenarios():
    """
    Executes the two mandatory pre-packaged demonstration scenarios
    for Ministry & team review using the Multi-Quantile ML Forecasting Engine.
    """
    print_banner()

    console.print("\n[bold cyan]========================================================================[/bold cyan]")
    console.print("[bold cyan]  PRESET DEMONSTRATION MODE: EXECUTING VERIFIED NATIONAL TRADE SCENARIOS [/bold cyan]")
    console.print("[bold cyan]========================================================================[/bold cyan]\n")

    # Scenario A: Deepwater Inbound Direct Discharge
    # 150,000T Coal from Hay Point (Australia) -> Dhamra Port (4 Voyages, 5% CVC discount)
    execute_evaluation(
        cargo_tonnage=150000.0,
        origin_name="Hay Point",
        destination_name="Dhamra",
        num_voyages=4,
        cvc_discount_pct=5.0,
        scenario_title="Scenario A: Deepwater Inbound Direct Discharge (150,000 MT Hay Point → Dhamra Port | Capesize)",
    )

    console.print("\n" + "─" * 80 + "\n")

    # Scenario B: Shallow Draft Transshipment Triggered
    # 75,000T Coal from Newcastle -> Haldia Port (Requires Sagar/Sandheads lighterage)
    # Using 7.5% negotiated discount to demonstrate the ₹4.2 Cr target headline savings
    execute_evaluation(
        cargo_tonnage=75000.0,
        origin_name="Newcastle",
        destination_name="Haldia",
        num_voyages=4,
        cvc_discount_pct=7.5,
        scenario_title="Scenario B: Shallow Draft Transshipment Triggered (75,000 MT Newcastle → Haldia Dock | Sagar STS)",
    )


def handle_update_data():
    """Polls live market proxies from Yahoo Finance and updates the local Parquet cache."""
    print_banner()
    from data.fetcher import MarketDataFetcher

    console.print("\n[bold cyan]▶ POLLING LIVE FREIGHT & COMMODITY PROXIES (YAHOO FINANCE / LOCAL CACHE)[/bold cyan]")
    fetcher = MarketDataFetcher()
    success, msg = fetcher.update_cache_from_network()

    if success:
        console.print(f"[bold green]✔ Status:[/bold green] {msg}")
    else:
        console.print(f"[bold red]✘ Status:[/bold red] {msg}")

    meta = fetcher.get_metadata()
    console.print(Panel(f"Parquet Store Status: {meta.get('data_source')}\nTotal Macro Records: {meta.get('macro_records')}\nLast Sync UTC: {meta.get('last_updated_utc')}", title="[bold cyan]Cache Metadata[/bold cyan]", border_style="cyan"))


def handle_train_ml():
    """Trains Multi-Quantile LightGBM models (p10, p50, p90) on local Parquet files."""
    print_banner()
    from engine.ml_forecaster import MultiQuantileForecaster

    console.print("\n[bold cyan]▶ TRAINING MULTI-QUANTILE LIGHTGBM MODELS (p10, p50, p90)[/bold cyan]")
    forecaster = MultiQuantileForecaster()
    results = forecaster.train_all_routes()

    table = Table(title="[bold]Trained Corridor Quantile Models[/bold]", box=box.ROUNDED, header_style="bold green")
    table.add_column("Trade Corridor", style="cyan")
    table.add_column("Quantiles Trained", style="bold yellow")
    table.add_column("Model Storage Path", style="dim")

    for r_code, q_dict in results.items():
        table.add_row(r_code, "p10, p50, p90 (α=0.10, 0.50, 0.90)", f"data/historical/models/{r_code}_*.joblib")

    console.print(table)
    console.print("[bold green]✔ All Multi-Quantile models successfully trained and persisted to disk.[/bold green]\n")


def handle_evaluate():
    """Runs full ML model evaluation: computes metrics and generates diagnostic plots."""
    print_banner()
    from engine.evaluator import run_full_evaluation
    from engine.ml_forecaster import ROUTE_COLUMN_MAPPING

    console.print("\n[bold cyan]▶ ML MODEL EVALUATION & DIAGNOSTIC VISUALISATION[/bold cyan]")
    console.print("[dim]  Computing MAE, RMSE, MAPE, R², Pinball Loss across all benchmark corridors…[/dim]\n")

    # Unique route codes
    route_codes = list(dict.fromkeys(ROUTE_COLUMN_MAPPING.values()))

    all_results = []
    for rc in route_codes:
        console.print(f"[bold yellow]  ▸ Evaluating:[/bold yellow] {rc}")
        try:
            result = run_full_evaluation(rc)
            all_results.append(result)
        except Exception as exc:
            console.print(f"  [bold red]✘ Failed:[/bold red] {rc} — {exc}")

    # Summary of generated artefacts
    from rich.table import Table
    from rich import box as rbox

    tbl = Table(
        title="[bold]Generated Diagnostic Reports[/bold]",
        box=rbox.ROUNDED,
        header_style="bold magenta",
        expand=True,
    )
    tbl.add_column("Plot", style="cyan")
    tbl.add_column("Saved At", style="dim white")

    if all_results:
        for path in all_results[0].get("plot_paths", []):
            tbl.add_row(os.path.basename(path), path)

    console.print(tbl)
    console.print("[bold green]✔ All evaluation artefacts saved to reports/plots/[/bold green]\n")


def main():
    parser = argparse.ArgumentParser(
        description="Ministry of Ports, Shipping and Waterways - Freight Procurement & Feasibility CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--demo",
        "--test-run",
        dest="demo",
        action="store_true",
        help="Execute interactive team presentation with 2 pre-packaged maritime scenarios.",
    )
    parser.add_argument(
        "--update-data",
        action="store_true",
        help="Poll live market proxies (GOGL, SBLK, Coal, Crude) and update local Parquet cache.",
    )
    parser.add_argument(
        "--train-ml",
        action="store_true",
        help="Retrain Multi-Quantile LightGBM models (p10, p50, p90) on historical Parquet data.",
    )
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="Run full ML model diagnostics: compute MAE/RMSE/MAPE/R²/Pinball and save plots to reports/plots/.",
    )
    parser.add_argument(
        "--cargo",
        type=float,
        default=75000.0,
        help="Cargo parcel weight in metric tons (e.g., 75000, 150000). Default: 75,000.",
    )
    parser.add_argument(
        "--origin",
        type=str,
        default="Newcastle",
        help="Origin loading port name or code (e.g., 'Hay Point', 'Newcastle', 'Taboneo'). Default: Newcastle.",
    )
    parser.add_argument(
        "--destination",
        type=str,
        default="Haldia",
        help="Destination discharge port name or code (e.g., 'Dhamra', 'Haldia', 'Paradip', 'Vizag'). Default: Haldia.",
    )
    parser.add_argument(
        "--voyages",
        type=int,
        default=4,
        help="Number of consecutive voyages to evaluate. Default: 4.",
    )
    parser.add_argument(
        "--cvc-discount",
        type=float,
        default=5.0,
        help="Negotiated CVC discount percentage against forward spot rates. Default: 5.0%%.",
    )
    parser.add_argument(
        "--target-cvc-rate",
        type=float,
        default=None,
        help="Explicit locked CVC freight rate in $/T (e.g. 18.40) to evaluate break-even sensitivity.",
    )

    args = parser.parse_args()

    if args.update_data:
        handle_update_data()
    elif args.train_ml:
        handle_train_ml()
    elif args.evaluate:
        handle_evaluate()
    elif args.demo:
        run_demo_scenarios()
    else:
        print_banner()
        execute_evaluation(
            cargo_tonnage=args.cargo,
            origin_name=args.origin,
            destination_name=args.destination,
            num_voyages=args.voyages,
            cvc_discount_pct=args.cvc_discount,
            target_cvc_rate=args.target_cvc_rate,
            scenario_title=f"Custom Evaluation: {args.cargo:,.0f} MT {args.origin} → {args.destination} ({args.voyages} Voyages)",
        )


if __name__ == "__main__":
    main()
