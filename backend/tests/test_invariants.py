"""Invariants that hold two modules together.

These are the tests worth having. Each one guards a coupling that is correct
today, invisible in either file on its own, and would fail silently rather than
loudly if someone changed one side.
"""

from __future__ import annotations

import pytest

from data import ingest
from models import project


def test_own_driver_matches_class_drivers():
    """A class must never regress on the series that derives its own target.

    ``freight.rate.<class>`` is computed from one proxy in data/ingest.py.
    models/project.py excludes that proxy from the same class's regressors. If
    the two drift apart the model fits a deterministic identity: near-perfect in
    sample, no information, and a backtest that looks excellent while predicting
    nothing. Nothing else in the codebase would notice.
    """
    metric_to_feature = {
        "baltic.bdi": "log_bdi",
        "equity.gogl": "log_gogl",
        "equity.sblk": "log_sblk",
    }

    for vessel_class, (driver_metric, _beta, _base, _why) in ingest.CLASS_DRIVERS.items():
        assert vessel_class in project.OWN_DRIVER, (
            f"{vessel_class} derives its rate from {driver_metric} but has no "
            "OWN_DRIVER entry, so it would regress on its own driver"
        )
        expected = metric_to_feature.get(driver_metric)
        assert expected is not None, (
            f"{driver_metric} drives {vessel_class} but is not mapped to a feature "
            "column here; add it so this invariant keeps checking"
        )
        assert project.OWN_DRIVER[vessel_class] == expected, (
            f"{vessel_class} is derived from {driver_metric} ({expected}) but excludes "
            f"{project.OWN_DRIVER[vessel_class]}"
        )


def test_own_driver_has_no_extra_classes():
    """The reverse direction: excluding a driver a class does not actually use
    throws away a real regressor for nothing."""
    assert set(project.OWN_DRIVER) == set(ingest.CLASS_DRIVERS)


def test_excluded_driver_is_absent_from_that_class_regressors():
    for vessel_class, excluded in project.OWN_DRIVER.items():
        features = project.exog_features_for(vessel_class)
        assert excluded not in features
        assert len(features) == len(project.FEATURES) - 1


def test_zim_never_reaches_the_dry_bulk_model():
    """ZIM is a container liner. It belongs to a different market with different
    demand drivers, and feeding it to a dry-bulk model imports noise as signal."""
    from data.adapters import equity

    assert "zim" in equity.MACRO_SENTIMENT_TICKERS
    assert "zim" not in equity.DRY_BULK_TICKERS
    assert not any("zim" in f for f in project.FEATURES)
    assert not any(
        "zim" in metric for metrics in project.FEATURE_METRICS.values() for metric in metrics
    )


def test_every_feature_column_has_a_source_or_comes_from_the_calendar():
    for column in project.FEATURES:
        assert column in project.FEATURE_METRICS or column in project.CALENDAR_FEATURES, (
            f"{column} is declared as a regressor but nothing fills it"
        )


def test_vessel_classes_agree_across_modules():
    from app.reference import VESSEL_SPECS

    assert {c.lower() for c in VESSEL_SPECS} == set(project.VESSEL_CLASSES)
    assert {c.lower() for c in VESSEL_SPECS} == set(ingest.CLASS_DRIVERS)


@pytest.mark.parametrize("adapter_name", ["baltic", "equity", "bunker", "congestion"])
def test_proxy_sources_declare_themselves(adapter_name):
    """Anything standing in for something it is not must say so, because the UI
    labels sources on this flag alone."""
    from data.adapters import adapter_metadata

    assert adapter_metadata()[adapter_name]["is_proxy"] is True


def test_non_proxy_sources_are_not_flagged():
    from data.adapters import adapter_metadata

    meta = adapter_metadata()
    for name in ("commodity", "macro", "weather", "ais"):
        assert meta[name]["is_proxy"] is False
