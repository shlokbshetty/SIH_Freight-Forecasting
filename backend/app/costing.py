"""Voyage costing and the spot versus consecutive-voyage-charter comparison.

A server-side port of src/lib/cvcEngine.ts. The difference that matters: the
frontend prices voyages off a static mock series, this prices them off whatever
the projection engine currently says, so the recommendation moves with the
market instead of with a hardcoded array.

Assumptions live in ASSUMPTIONS below rather than being scattered through the
arithmetic, so a chartering desk can argue with the numbers without reading the
code.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.reference import (
    DISCHARGE_PORTS_BY_ID,
    LOADING_PORTS_BY_ID,
    VESSEL_SPECS,
    DischargePort,
    resolve_port_key,
)
from data.ports import resolver
from data.ports.schema import berths_for_port

# ── Assumptions ───────────────────────────────────────────────────────────────

USD_INR = 88.4
CRORE = 1e7

BUNKER_LADEN_TPD = {"Handysize": 21, "Supramax": 27, "Panamax": 32, "Capesize": 45}
BALLAST_BURN_FACTOR = 0.82
BUNKER_PORT_TPD = 4.5
BUNKER_BASIS_USD = 620.0
CVC_BAF_HEDGE = 0.7

# Port physics lives in data/ports/resolver.py; re-exported so callers that
# want the constant do not need to know where it lives.
TONNES_PER_CM = resolver.TONNES_PER_CM
UKC_MARGIN_M = resolver.UKC_MARGIN_M

#: Default demurrage exposure when a caller does not state one, USD per day.
DEFAULT_DEMURRAGE_USD_PER_DAY = 22_000.0

SPOT_WAIT_DAYS = {"low": 1.2, "medium": 2.9, "high": 5.4}
CVC_WAIT_REDUCTION = 0.45
FIXED_TURNAROUND_DAYS = 2.0
ROUTING_FACTOR = 1.18

DISCHARGE_PORT_CHARGES = {
    "paradip": (1.35, 58_000), "vizag": (1.48, 62_000), "gangavaram": (1.55, 66_000),
    "gopalpur": (1.20, 44_000), "dhamra": (1.42, 60_000),
    "sagar-sandheads": (0.95, 38_000), "haldia": (1.62, 54_000),
}
DEFAULT_DISCHARGE_CHARGE = (1.40, 55_000)

LOAD_PORT_TERMS = {
    "newcastle": (0.78, 46_000, 60_000), "gladstone": (0.82, 44_000, 55_000),
    "abbot-point": (0.80, 42_000, 50_000), "hampton-roads": (0.95, 52_000, 48_000),
    "beira": (1.10, 38_000, 18_000), "nacala": (1.05, 40_000, 22_000),
    "murmansk": (1.15, 50_000, 30_000), "kalimantan": (0.72, 34_000, 35_000),
    "balikpapan": (0.75, 36_000, 32_000),
}
DEFAULT_LOAD_TERMS = (0.90, 44_000, 40_000)

#: Forecast errors travel together across months, so averaging N voyages
#: reduces uncertainty far less than independent draws would.
RATE_ERROR_CORRELATION = 0.7
BAND_Z = 1.645

# ── Period time charter ───────────────────────────────────────────────────────
#
# A third structure, and a genuinely different risk shape. On a voyage charter
# the owner sells a delivered tonne and carries the fuel and the schedule. On a
# period time charter the charterer hires the ship by the day and takes both:
# no demurrage, because the waiting is their own time, but the full bunker bill
# and every idle and ballast day on their account.

#: Indicative daily hire, USD per day.
TC_HIRE_USD_PER_DAY = {
    "Handysize": 11_000.0,
    "Supramax": 14_200.0,
    "Panamax": 17_400.0,
    "Capesize": 26_500.0,
}

#: Days lost to breakdown, survey and drydock over a period charter, as a share.
TC_OFFHIRE_ALLOWANCE = 0.02

#: Address commission and brokerage on hire.
TC_COMMISSION = 0.0375


def usd_to_crore(usd: float) -> float:
    return (usd * USD_INR) / CRORE


def haversine_nm(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    radius = 3440.065
    d_lat = math.radians(b_lat - a_lat)
    d_lng = math.radians(b_lng - a_lng)
    h = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(a_lat)) * math.cos(math.radians(b_lat)) * math.sin(d_lng / 2) ** 2
    )
    return 2 * radius * math.asin(min(1.0, math.sqrt(h)))


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# ── Constraint engine ─────────────────────────────────────────────────────────
#
# There is one implementation of berth eligibility and lighterage, and it lives
# in data/ports/resolver.py against the berth-level table. This module used to
# carry a second copy working off a single draft per port. It does not any more:
# two implementations of the same rule drift, and the one that drifts is always
# the one the money runs through.

def laden_draft_at(vessel_class: str, cargo_tonnes: float) -> float:
    return resolver.laden_draft_at_class(vessel_class, cargo_tonnes)


def plan_call(
    port_id: str, commodity: str, vessel_class: str, cargo_tonnes: float
) -> resolver.BerthResolution:
    """Resolve the discharge call against the berth table."""
    _pid, berth_port = resolve_port_key(port_id)
    spec = VESSEL_SPECS[vessel_class]
    return resolver.resolve_berth(
        berth_port,
        commodity,
        laden_draft_at(vessel_class, cargo_tonnes),
        cargo_tonnes,
        loa_m=spec.loa_m,
        beam_m=spec.beam_m,
    )


@dataclass
class CallEconomics:
    """What the resolved call costs in days and dollars."""

    outcome: str
    berth_id: str | None
    berth_name: str | None
    discharge_rate_tpd: int
    lighterage_tonnes: float
    lighterage_days: float
    lighterage_cost_usd: float
    tide_wait_days: float
    blocked_reason: str | None
    reason: str
    provenance: dict


def call_economics(resolution: resolver.BerthResolution, fallback_rate_tpd: int = 15_000) -> CallEconomics:
    berth = resolution.berth
    plan = resolution.lighterage

    if berth is not None:
        rate = berth.discharge_rate_tpd or fallback_rate_tpd
        # A tide-bound berth buys waiting. Half a spring cycle is the
        # conventional planning allowance.
        tide_wait = 0.5 if resolution.outcome is resolver.Outcome.ACCEPT_HIGH_TIDE_ONLY else 0.0
        blocked = None
        provenance = {"source_url": berth.source_url, "source_date": berth.source_date}
    elif plan is not None and plan.onward_berth_id:
        onward = next(
            (b for b in berths_for_port(resolution.port) if b.berth_id == plan.onward_berth_id), None
        )
        rate = (onward.discharge_rate_tpd if onward else 0) or fallback_rate_tpd
        tide_wait = 0.0
        blocked = None
        provenance = {"source_url": plan.source_url, "source_date": plan.source_date}
    else:
        rate = fallback_rate_tpd
        tide_wait = 0.0
        blocked = resolution.reason
        provenance = {}

    return CallEconomics(
        outcome=resolution.outcome.value,
        berth_id=berth.berth_id if berth else (plan.onward_berth_id if plan else None),
        berth_name=berth.berth_name if berth else (plan.node_name if plan else None),
        discharge_rate_tpd=rate,
        lighterage_tonnes=plan.tonnes_to_lighten if plan else 0.0,
        lighterage_days=plan.added_days if plan else 0.0,
        lighterage_cost_usd=plan.cost_usd if plan else 0.0,
        tide_wait_days=tide_wait,
        blocked_reason=blocked,
        reason=resolution.reason,
        provenance=provenance,
    )


# ── Voyage profile ────────────────────────────────────────────────────────────

@dataclass
class VoyageProfile:
    distance_nm: float
    sea_days: float
    cargo_days: float
    wait_days_spot: float
    wait_days_cvc: float
    round_trip_days: float
    bunker_tonnes: float


def build_profile(
    load_port_id: str,
    port: DischargePort,
    vessel_class: str,
    cargo_tonnes: float,
    call: CallEconomics,
    observed_wait_days: float | None = None,
) -> VoyageProfile:
    spec = VESSEL_SPECS[vessel_class]
    load = LOADING_PORTS_BY_ID.get(load_port_id)
    _, _, load_rate = LOAD_PORT_TERMS.get(load_port_id, DEFAULT_LOAD_TERMS)

    direct = haversine_nm(load.lat, load.lng, port.lat, port.lng) if load else 4_000.0
    distance = direct * ROUTING_FACTOR

    leg_days = distance / (spec.speed_kts * 24)
    sea_days = leg_days * 2

    # Discharge speed now comes from the berth she actually goes to, not from a
    # single figure averaged over the whole port.
    cargo_days = cargo_tonnes / load_rate + cargo_tonnes / max(1, call.discharge_rate_tpd)

    wait_spot = (
        observed_wait_days
        if observed_wait_days is not None
        else SPOT_WAIT_DAYS[port.congestion_level]
    ) + call.tide_wait_days
    wait_cvc = wait_spot * (1 - CVC_WAIT_REDUCTION)

    bunker_tonnes = (
        leg_days * BUNKER_LADEN_TPD[vessel_class]
        + leg_days * BUNKER_LADEN_TPD[vessel_class] * BALLAST_BURN_FACTOR
        + (cargo_days + wait_spot + FIXED_TURNAROUND_DAYS + call.lighterage_days) * BUNKER_PORT_TPD
    )

    return VoyageProfile(
        distance, sea_days, cargo_days, wait_spot, wait_cvc,
        sea_days + cargo_days + wait_spot + FIXED_TURNAROUND_DAYS + call.lighterage_days,
        bunker_tonnes,
    )


# ── The comparison ────────────────────────────────────────────────────────────

def evaluate(
    *,
    load_port_id: str,
    discharge_port_id: str,
    vessel_class: str,
    cargo_tonnes: float,
    num_voyages: int,
    bunker_price_usd: float,
    demurrage_usd_per_day: float,
    cvc_discount_pct: float,
    market_rate_usd_per_t: float,
    voyage_rates: list[float],
    voyage_rate_sd: list[float],
    commodity: str = "thermal_coal",
    observed_wait_days: float | None = None,
) -> dict:
    """Price the programme both ways.

    ``voyage_rates`` and ``voyage_rate_sd`` come from the projection engine, one
    entry per voyage, sampled at that voyage's departure. Passing them in keeps
    this function pure and testable with no model or database attached.
    """
    port = DISCHARGE_PORTS_BY_ID.get(discharge_port_id) or DISCHARGE_PORTS_BY_ID["paradip"]
    load = LOADING_PORTS_BY_ID.get(load_port_id)

    resolution = plan_call(discharge_port_id, commodity, vessel_class, cargo_tonnes)
    call = call_economics(resolution)
    profile = build_profile(
        load_port_id, port, vessel_class, cargo_tonnes, call, observed_wait_days
    )

    load_per_mt, load_call, _ = LOAD_PORT_TERMS.get(load_port_id, DEFAULT_LOAD_TERMS)
    disc_per_mt, disc_call = DISCHARGE_PORT_CHARGES.get(discharge_port_id, DEFAULT_DISCHARGE_CHARGE)
    port_charges = load_per_mt * cargo_tonnes + load_call + disc_per_mt * cargo_tonnes + disc_call

    demurrage_spot = profile.wait_days_spot * demurrage_usd_per_day
    demurrage_cvc = profile.wait_days_cvc * demurrage_usd_per_day

    # Freight is all-in, so this line carries only the deviation from the
    # market's bunker basis, which is what a BAF clause actually settles.
    bunker_deviation = profile.bunker_tonnes * (bunker_price_usd - BUNKER_BASIS_USD)
    bunker_spot = bunker_deviation
    bunker_cvc = bunker_deviation * (1 - CVC_BAF_HEDGE)

    locked_rate = market_rate_usd_per_t * (1 - cvc_discount_pct / 100)

    rates = (voyage_rates or [market_rate_usd_per_t])[:num_voyages]
    while len(rates) < num_voyages:
        rates.append(rates[-1])

    freight_spot = sum(r * cargo_tonnes for r in rates)
    freight_cvc = locked_rate * cargo_tonnes * num_voyages

    non_freight_spot = (bunker_spot + port_charges + demurrage_spot + call.lighterage_cost_usd) * num_voyages
    non_freight_cvc = (bunker_cvc + port_charges + demurrage_cvc + call.lighterage_cost_usd) * num_voyages

    spot_total = freight_spot + non_freight_spot
    cvc_total = freight_cvc + non_freight_cvc
    delta_cr = usd_to_crore(spot_total - cvc_total)

    # The average spot rate at which both programmes cost the same.
    break_even = (cvc_total - non_freight_spot) / max(1.0, cargo_tonnes * num_voyages)

    mean_rate = sum(rates) / len(rates)
    sds = (voyage_rate_sd or [0.0])[:num_voyages] or [0.0]
    sd_per_voyage = sum(sds) / len(sds)
    sd = sd_per_voyage * math.sqrt(
        (1 + (num_voyages - 1) * RATE_ERROR_CORRELATION) / max(1, num_voyages)
    )
    # The forecast's 90% band, repriced as a whole programme.
    low_avg = max(0.0, mean_rate - BAND_Z * sd_per_voyage)
    high_avg = mean_rate + BAND_Z * sd_per_voyage
    low_delta_cr = usd_to_crore(low_avg * cargo_tonnes * num_voyages + non_freight_spot) - usd_to_crore(cvc_total)
    high_delta_cr = usd_to_crore(high_avg * cargo_tonnes * num_voyages + non_freight_spot) - usd_to_crore(cvc_total)

    cvc_wins = delta_cr >= 0
    prob_spot_wins = normal_cdf((break_even - mean_rate) / sd) if sd > 0 else (0.0 if cvc_wins else 1.0)

    def cr(usd: float) -> float:
        return round(usd_to_crore(usd), 3)

    line_items = [
        {
            "label": "Base freight",
            "spot_cr": cr(freight_spot), "cvc_cr": cr(freight_cvc),
            "note": f"${mean_rate:.2f}/T average forecast vs ${locked_rate:.2f}/T locked",
        },
        {
            "label": "Bunker adjustment",
            "spot_cr": cr(bunker_spot * num_voyages), "cvc_cr": cr(bunker_cvc * num_voyages),
            "note": (
                f"{profile.bunker_tonnes:,.0f} T VLSFO per voyage, deviation from the "
                f"${BUNKER_BASIS_USD:,.0f}/T basis, {CVC_BAF_HEDGE:.0%} hedged under the CVC"
            ),
        },
        {
            "label": "Port charges",
            "spot_cr": cr(port_charges * num_voyages), "cvc_cr": cr(port_charges * num_voyages),
            "note": f"{load.name if load else load_port_id} load plus {port.name} discharge, identical either way",
        },
        {
            "label": "Expected demurrage",
            "spot_cr": cr(demurrage_spot * num_voyages), "cvc_cr": cr(demurrage_cvc * num_voyages),
            "note": (
                f"{profile.wait_days_spot:.1f} d expected wait on spot vs "
                f"{profile.wait_days_cvc:.1f} d on a nominated berth window"
            ),
        },
        {
            "label": "Lighterage",
            "spot_cr": cr(call.lighterage_cost_usd * num_voyages),
            "cvc_cr": cr(call.lighterage_cost_usd * num_voyages),
            "note": (
                resolution.lighterage.narrative if resolution.lighterage
                else "Draft clears the berth; no transhipment"
            ),
        },
    ]

    # ── Period time charter, priced over the same programme ────────────────
    programme_days = profile.round_trip_days * num_voyages
    hire_days = programme_days * (1 + TC_OFFHIRE_ALLOWANCE)
    hire_rate = TC_HIRE_USD_PER_DAY.get(vessel_class, 15_000.0)
    tc_hire = hire_rate * hire_days * (1 + TC_COMMISSION)
    # The charterer buys the fuel outright, not a deviation from a basis.
    tc_bunkers = profile.bunker_tonnes * bunker_price_usd * num_voyages
    tc_non_freight = (port_charges + call.lighterage_cost_usd) * num_voyages
    tc_total = tc_hire + tc_bunkers + tc_non_freight
    tc_delta_cr = usd_to_crore(spot_total - tc_total)

    magnitude = abs(delta_cr)
    figure = f"{magnitude:.1f}" if magnitude >= 10 else f"{magnitude:.2f}"
    plural = "" if num_voyages == 1 else "s"
    if cvc_wins:
        headline = (
            f"CVC saves Rs {figure} Cr across {num_voyages} voyage{plural}. "
            f"Spot only wins if rates fall below ${break_even:.2f}/T, and our forecast "
            f"puts that probability at {prob_spot_wins * 100:.0f}%."
        )
    else:
        headline = (
            f"Spot beats CVC by Rs {figure} Cr across {num_voyages} voyage{plural}. "
            f"The lock only pays if rates hold above ${break_even:.2f}/T, and our forecast "
            f"puts that probability at {(1 - prob_spot_wins) * 100:.0f}%."
        )

    cheapest = min(
        (("spot", spot_total), ("cvc", cvc_total), ("ptc", tc_total)),
        key=lambda pair: pair[1],
    )[0]

    return {
        "route": f"{load.name if load else load_port_id} to {port.name}",
        "vessel_class": vessel_class,
        "num_voyages": num_voyages,
        "spot_total_cr": round(usd_to_crore(spot_total), 3),
        "cvc_total_cr": round(usd_to_crore(cvc_total), 3),
        "delta_cr": round(delta_cr, 3),
        "break_even_usd_per_t": round(break_even, 3),
        "prob_spot_wins": round(prob_spot_wins, 4),
        "locked_rate_usd_per_t": round(locked_rate, 3),
        "market_rate_usd_per_t": round(market_rate_usd_per_t, 3),
        "forecast_avg_usd_per_t": round(mean_rate, 3),
        "line_items": line_items,
        "lighterage_tonnes": round(call.lighterage_tonnes, 1),
        "blocked_reason": call.blocked_reason,
        "berth": {
            "outcome": call.outcome,
            "berth_id": call.berth_id,
            "berth_name": call.berth_name,
            "discharge_rate_tpd": call.discharge_rate_tpd,
            "reason": call.reason,
            "provenance": call.provenance,
        },
        "headline": headline,
        "cheapest_structure": cheapest,
        "ptc": {
            "hire_usd_per_day": round(hire_rate, 2),
            "hire_days": round(hire_days, 2),
            "programme_days": round(programme_days, 2),
            "hire_cr": round(usd_to_crore(tc_hire), 3),
            "bunkers_cr": round(usd_to_crore(tc_bunkers), 3),
            "port_and_lighterage_cr": round(usd_to_crore(tc_non_freight), 3),
            "total_cr": round(usd_to_crore(tc_total), 3),
            "vs_spot_cr": round(tc_delta_cr, 3),
            "vs_cvc_cr": round(usd_to_crore(cvc_total - tc_total), 3),
            "note": (
                "Charterer buys the fuel and owns the waiting: no demurrage, full bunker "
                f"exposure, {TC_OFFHIRE_ALLOWANCE:.0%} off-hire allowed, "
                f"{TC_COMMISSION:.2%} commission on hire."
            ),
        },
        "voyages": [
            {
                "index": i + 1,
                "departure_day": int(round(i * profile.round_trip_days)),
                "rate_usd_per_t": round(rate, 3),
                "spot_cr": round(usd_to_crore(rate * cargo_tonnes + bunker_spot + port_charges + demurrage_spot + call.lighterage_cost_usd), 3),
                "cvc_cr": round(usd_to_crore(locked_rate * cargo_tonnes + bunker_cvc + port_charges + demurrage_cvc + call.lighterage_cost_usd), 3),
            }
            for i, rate in enumerate(rates)
        ],
        "band": {
            "low_avg_rate": round(low_avg, 3),
            "high_avg_rate": round(high_avg, 3),
            "low_delta_cr": round(low_delta_cr, 3),
            "high_delta_cr": round(high_delta_cr, 3),
        },
        "rate_distribution": {"mean": round(mean_rate, 3), "sd": round(sd, 4)},
        "profile": {
            "distance_nm": round(profile.distance_nm, 1),
            "sea_days": round(profile.sea_days, 2),
            "cargo_days": round(profile.cargo_days, 2),
            "wait_days_spot": round(profile.wait_days_spot, 2),
            "round_trip_days": round(profile.round_trip_days, 2),
            "bunker_tonnes": round(profile.bunker_tonnes, 1),
        },
    }


# ── Multi-port discharge ──────────────────────────────────────────────────────
#
# Load one cargo, discharge it across two ports. Worth doing for two different
# reasons, and the model has to separate them:
#
#   Reach.  A ship too deep for the shallower port can often serve it anyway by
#           discharging the first parcel at the deeper port and arriving at the
#           second already lightened. The sea does the lightering for free.
#   Cost.   Two calls cost two sets of port charges and a leg of steaming
#           between them. That has to beat whatever the single-port answer was,
#           which is frequently a smaller ship or a barge bill.

#: Extra days per additional discharge call, for shifting and formalities.
EXTRA_CALL_DAYS = 1.25


def evaluate_multiport(
    *,
    load_port_id: str,
    discharge_port_ids: list[str],
    vessel_class: str,
    total_tonnes: float,
    commodity: str,
    rate_usd_per_t: float,
    bunker_price_usd: float,
    demurrage_usd_per_day: float,
    steps: int = 8,
) -> dict:
    """Compare discharging everything at one port against splitting across two.

    The split grid is coarse on purpose. Parcels are negotiated in round numbers,
    and an optimum quoted to the tonne would be false precision.
    """
    if len(discharge_port_ids) < 2:
        raise ValueError("multi-port needs at least two discharge ports")

    first_id, second_id = discharge_port_ids[0], discharge_port_ids[1]
    first = DISCHARGE_PORTS_BY_ID.get(first_id)
    second = DISCHARGE_PORTS_BY_ID.get(second_id)
    if first is None or second is None:
        raise ValueError("unknown discharge port")

    spec = VESSEL_SPECS[vessel_class]

    def call_at(port_id: str, port: DischargePort, tonnes_aboard: float, tonnes_to_discharge: float) -> dict:
        """Resolve a call with the ship carrying `tonnes_aboard` on arrival."""
        _pid, berth_port = resolve_port_key(port_id)
        arrival_draft = resolver.laden_draft_at_class(vessel_class, tonnes_aboard)
        resolution = resolver.resolve_berth(
            berth_port, commodity, arrival_draft, tonnes_aboard,
            loa_m=spec.loa_m, beam_m=spec.beam_m,
        )
        econ = call_economics(resolution)
        per_mt, fixed = DISCHARGE_PORT_CHARGES.get(port_id, DEFAULT_DISCHARGE_CHARGE)
        charges = per_mt * tonnes_to_discharge + fixed
        wait = SPOT_WAIT_DAYS[port.congestion_level] + econ.tide_wait_days
        days = wait + tonnes_to_discharge / max(1, econ.discharge_rate_tpd) + econ.lighterage_days
        return {
            "port_id": port_id,
            "port_name": port.name,
            "tonnes": round(tonnes_to_discharge, 1),
            "arrival_draft_m": round(arrival_draft, 2),
            "outcome": econ.outcome,
            "berth_id": econ.berth_id,
            "berth_name": econ.berth_name,
            "reason": econ.reason,
            "lighterage_tonnes": round(econ.lighterage_tonnes, 1),
            "lighterage_cost_usd": round(econ.lighterage_cost_usd, 2),
            "port_charges_usd": round(charges, 2),
            "days": round(days, 2),
            "demurrage_usd": round(wait * demurrage_usd_per_day, 2),
            "blocked": econ.blocked_reason is not None,
            "provenance": econ.provenance,
        }

    load_per_mt, load_call_usd, load_rate_tpd = LOAD_PORT_TERMS.get(load_port_id, DEFAULT_LOAD_TERMS)
    load_side = load_per_mt * total_tonnes + load_call_usd
    load_days = total_tonnes / load_rate_tpd
    freight = rate_usd_per_t * total_tonnes

    inter_port_nm = haversine_nm(first.lat, first.lng, second.lat, second.lng) * ROUTING_FACTOR
    inter_port_days = inter_port_nm / (spec.speed_kts * 24)

    def bunkers_for(days: float) -> float:
        # Sea days burn at service rate, port days on auxiliaries. Approximated
        # here by treating the extra leg as sea time and the rest as port time.
        return days * BUNKER_PORT_TPD * bunker_price_usd

    # ── Baseline: everything at the first port ────────────────────────────────
    base_call = call_at(first_id, first, total_tonnes, total_tonnes)
    base_total = (
        freight + load_side + base_call["port_charges_usd"]
        + base_call["demurrage_usd"] + base_call["lighterage_cost_usd"]
    )
    baseline = {
        "label": f"All {total_tonnes:,.0f} T at {first.name}",
        "calls": [base_call],
        "total_usd": round(base_total, 2),
        "total_cr": round(usd_to_crore(base_total), 3),
        "port_days": round(load_days + base_call["days"], 2),
        "feasible": not base_call["blocked"],
    }

    # ── Splits ────────────────────────────────────────────────────────────────
    options: list[dict] = []
    for i in range(1, steps):
        first_share = i / steps
        first_tonnes = round(total_tonnes * first_share, -2)
        second_tonnes = total_tonnes - first_tonnes
        if first_tonnes <= 0 or second_tonnes <= 0:
            continue

        call_one = call_at(first_id, first, total_tonnes, first_tonnes)
        # She arrives at the second port already lightened by the first parcel.
        call_two = call_at(second_id, second, second_tonnes, second_tonnes)

        extra_days = inter_port_days + EXTRA_CALL_DAYS
        total = (
            freight + load_side
            + call_one["port_charges_usd"] + call_two["port_charges_usd"]
            + call_one["demurrage_usd"] + call_two["demurrage_usd"]
            + call_one["lighterage_cost_usd"] + call_two["lighterage_cost_usd"]
            + bunkers_for(extra_days)
        )
        options.append({
            "label": f"{first_tonnes:,.0f} T at {first.name}, {second_tonnes:,.0f} T at {second.name}",
            "first_tonnes": first_tonnes,
            "second_tonnes": second_tonnes,
            "calls": [call_one, call_two],
            "extra_days": round(extra_days, 2),
            "total_usd": round(total, 2),
            "total_cr": round(usd_to_crore(total), 3),
            "port_days": round(load_days + call_one["days"] + call_two["days"] + extra_days, 2),
            "feasible": not call_one["blocked"] and not call_two["blocked"],
            "vs_baseline_cr": round(usd_to_crore(total - base_total), 3),
        })

    feasible = [o for o in options if o["feasible"]]
    best = min(feasible, key=lambda o: o["total_usd"]) if feasible else None

    if best is None:
        verdict = (
            f"No workable split across {first.name} and {second.name} for a {vessel_class} "
            f"carrying {total_tonnes:,.0f} T of {commodity}."
        )
    elif not baseline["feasible"]:
        verdict = (
            f"{vessel_class} cannot discharge the full parcel at {first.name}, but splitting works: "
            f"{best['label']} at Rs {best['total_cr']:.2f} Cr."
        )
    elif best["total_usd"] < base_total:
        verdict = (
            f"Splitting saves Rs {abs(best['vs_baseline_cr']):.2f} Cr against a single call at "
            f"{first.name}. {best['label']}."
        )
    else:
        verdict = (
            f"A single call at {first.name} stays cheapest. The best split costs "
            f"Rs {best['vs_baseline_cr']:.2f} Cr more, mostly the second set of port charges."
        )

    return {
        "vessel_class": vessel_class,
        "commodity": commodity,
        "total_tonnes": int(total_tonnes),
        "rate_usd_per_t": round(rate_usd_per_t, 3),
        "inter_port_nm": round(inter_port_nm, 1),
        "inter_port_days": round(inter_port_days, 2),
        "baseline": baseline,
        "options": options,
        "best": best,
        "verdict": verdict,
    }
