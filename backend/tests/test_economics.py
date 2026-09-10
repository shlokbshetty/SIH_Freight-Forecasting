"""Economic invariants of the spot versus CVC comparison.

Ported from the evaluator branch's property tests when that engine was retired.
The implementation they guarded is gone; the invariants they encode are
properties of the trade itself and hold for any correct engine, so they now run
against app/costing.py.
"""

from __future__ import annotations

import pytest

from app import costing

BASE = dict(
    load_port_id="newcastle",
    discharge_port_id="paradip",
    vessel_class="Supramax",
    cargo_tonnes=55_000,
    num_voyages=4,
    bunker_price_usd=620.0,
    demurrage_usd_per_day=22_000.0,
    commodity="thermal_coal",
)


def evaluate(**overrides):
    args = dict(BASE)
    args.update(overrides)
    rate = args.pop("rate", 18.40)
    voyages = args["num_voyages"]
    args.setdefault("market_rate_usd_per_t", rate)
    args.setdefault("voyage_rates", [rate] * voyages)
    args.setdefault("voyage_rate_sd", [rate * 0.07] * voyages)
    args.setdefault("cvc_discount_pct", 5.0)
    return costing.evaluate(**args)


# ── The break-even identity ───────────────────────────────────────────────────

def test_at_the_break_even_rate_both_programmes_cost_the_same():
    """The defining property. If it does not hold, the headline number is wrong
    and so is every probability derived from it."""
    first = evaluate()
    break_even = first["break_even_usd_per_t"]

    repriced = evaluate(rate=break_even, market_rate_usd_per_t=first["market_rate_usd_per_t"])
    assert repriced["spot_total_cr"] == pytest.approx(repriced["cvc_total_cr"], abs=0.01)
    assert repriced["delta_cr"] == pytest.approx(0.0, abs=0.01)


@pytest.mark.parametrize("discount", [0.0, 2.5, 5.0, 10.0, 15.0])
def test_break_even_identity_holds_across_discounts(discount):
    first = evaluate(cvc_discount_pct=discount)
    repriced = evaluate(
        rate=first["break_even_usd_per_t"],
        market_rate_usd_per_t=first["market_rate_usd_per_t"],
        cvc_discount_pct=discount,
    )
    assert repriced["delta_cr"] == pytest.approx(0.0, abs=0.01)


def test_spot_above_break_even_favours_the_lock():
    first = evaluate()
    be = first["break_even_usd_per_t"]
    market = first["market_rate_usd_per_t"]

    dearer = evaluate(rate=be + 2.0, market_rate_usd_per_t=market)
    cheaper = evaluate(rate=be - 2.0, market_rate_usd_per_t=market)

    assert dearer["delta_cr"] > 0, "spot above break-even must make the CVC cheaper"
    assert cheaper["delta_cr"] < 0, "spot below break-even must make spot cheaper"


# ── Discount monotonicity ─────────────────────────────────────────────────────

def test_zero_discount_locks_at_the_market_rate():
    r = evaluate(cvc_discount_pct=0.0)
    assert r["locked_rate_usd_per_t"] == pytest.approx(r["market_rate_usd_per_t"], abs=1e-6)


def test_locked_rate_falls_monotonically_with_discount():
    discounts = [0.0, 2.5, 5.0, 7.5, 10.0, 12.5, 15.0]
    rates = [evaluate(cvc_discount_pct=d)["locked_rate_usd_per_t"] for d in discounts]
    assert rates == sorted(rates, reverse=True)
    assert all(a > b for a, b in zip(rates, rates[1:]))


def test_a_deeper_discount_never_makes_the_cvc_worse():
    discounts = [0.0, 5.0, 10.0, 15.0]
    deltas = [evaluate(cvc_discount_pct=d)["delta_cr"] for d in discounts]
    assert deltas == sorted(deltas), "saving must increase, or hold, as the discount deepens"


def test_a_fifteen_percent_discount_cuts_the_rate_by_fifteen_percent():
    base = evaluate(cvc_discount_pct=0.0)["locked_rate_usd_per_t"]
    cut = evaluate(cvc_discount_pct=15.0)["locked_rate_usd_per_t"]
    assert cut == pytest.approx(base * 0.85, rel=1e-6)


def test_break_even_falls_as_the_discount_deepens():
    """A cheaper lock is harder for spot to beat, so the bar drops."""
    values = [evaluate(cvc_discount_pct=d)["break_even_usd_per_t"] for d in (0.0, 5.0, 10.0, 15.0)]
    assert all(a > b for a, b in zip(values, values[1:]))


# ── Scale and structure ───────────────────────────────────────────────────────

def test_totals_scale_with_the_number_of_voyages():
    one = evaluate(num_voyages=1)
    four = evaluate(num_voyages=4)
    assert four["spot_total_cr"] == pytest.approx(one["spot_total_cr"] * 4, rel=1e-6)
    assert four["cvc_total_cr"] == pytest.approx(one["cvc_total_cr"] * 4, rel=1e-6)


def test_probability_is_a_probability():
    for discount in (0.0, 5.0, 15.0):
        p = evaluate(cvc_discount_pct=discount)["prob_spot_wins"]
        assert 0.0 <= p <= 1.0


def test_bunkers_at_the_contract_basis_cancel_out():
    """The bunker line carries the deviation from the basis, not the whole bill,
    so at the basis price it must contribute nothing to either side."""
    r = evaluate(bunker_price_usd=costing.BUNKER_BASIS_USD)
    line = next(i for i in r["line_items"] if i["label"] == "Bunker adjustment")
    assert line["spot_cr"] == pytest.approx(0.0, abs=1e-6)
    assert line["cvc_cr"] == pytest.approx(0.0, abs=1e-6)


def test_dearer_bunkers_favour_the_hedged_contract():
    cheap = evaluate(bunker_price_usd=450.0)["delta_cr"]
    dear = evaluate(bunker_price_usd=850.0)["delta_cr"]
    assert dear > cheap, "the CVC's bunker clause must be worth more when fuel is dear"


def test_period_time_charter_is_priced_and_comparable():
    r = evaluate()
    ptc = r["ptc"]
    assert ptc is not None
    assert ptc["total_cr"] > 0
    assert ptc["hire_cr"] > 0
    # The charterer buys the fuel outright on a time charter, so the bunker line
    # is the whole bill rather than a deviation, and cannot be zero.
    assert ptc["bunkers_cr"] > 0
    assert r["cheapest_structure"] in {"spot", "cvc", "ptc"}


def test_line_items_sum_to_the_totals():
    r = evaluate()
    assert sum(i["spot_cr"] for i in r["line_items"]) == pytest.approx(r["spot_total_cr"], abs=0.02)
    assert sum(i["cvc_cr"] for i in r["line_items"]) == pytest.approx(r["cvc_total_cr"], abs=0.02)
