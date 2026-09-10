# -*- coding: utf-8 -*-
"""
Unit and integration tests for the Machine Learning Freight Forecasting Engine:
1. Parquet storage read/write operations
2. Feature engineering pipeline (lags, rolling volatility, seasonal indicators)
3. Multi-quantile LightGBM regressor (p10 <= p50 <= p90 monotonicity)
4. Empirical break-even probability CDF bounds
5. Financial evaluator integration with ML confidence intervals
6. CLI presentation handlers
"""

import os
import pytest
import pandas as pd
import numpy as np

from data.fetcher import (
    MarketDataFetcher,
    MACRO_PARQUET,
    ROUTE_PARQUET,
    METADATA_JSON,
)
from data.features import FreightFeatureEngineer
from engine.ml_forecaster import (
    MultiQuantileForecaster,
    MLForecastResult,
)
from engine.financial_evaluator import FinancialEvaluator
from data.ports import get_port
from data.vessels import get_vessel_class
import cli


# ======================================================================
# 1. Parquet Storage & Caching Tests
# ======================================================================

def test_parquet_io_and_metadata():
    """Verify Parquet datasets and metadata structure exist and load cleanly."""
    fetcher = MarketDataFetcher()
    macro_df = fetcher.load_macro_data()
    route_df = fetcher.load_route_data()
    meta = fetcher.get_metadata()

    assert isinstance(macro_df, pd.DataFrame)
    assert isinstance(route_df, pd.DataFrame)
    assert len(macro_df) > 0
    assert len(route_df) > 0

    # Verify essential columns
    for col in ["GOGL", "SBLK", "COAL_NEWCASTLE", "BRENT_CRUDE", "USD_INR"]:
        assert col in macro_df.columns

    for r_col in [
        "NEWCASTLE_HALDIA_PANAMAX",
        "HAY_POINT_DHAMRA_CAPESIZE",
        "TABONEO_VIZAG_SUPRAMAX",
    ]:
        assert r_col in route_df.columns

    # Verify metadata JSON
    assert "data_source" in meta
    assert "last_updated_utc" in meta


def test_offline_first_resilience():
    """Verify fetcher update handles network errors gracefully without crashing."""
    fetcher = MarketDataFetcher()
    success, msg = fetcher.update_cache_from_network()
    # Offline-first policy guarantees success=True with cached fallback
    assert success is True
    assert isinstance(msg, str)


# ======================================================================
# 2. Feature Engineering Pipeline Tests
# ======================================================================

def test_feature_engineering_lags_and_rolling():
    """Verify lag generation, moving averages, and rolling volatility."""
    fe = FreightFeatureEngineer()
    macro_df = fe.fetcher.load_macro_data()
    feat_df = fe.engineer_macro_features(macro_df)

    assert len(feat_df) > 0

    # Check lag columns
    for lag in [1, 7, 14, 30]:
        assert f"GOGL_lag_{lag}" in feat_df.columns
        assert f"COAL_NEWCASTLE_lag_{lag}" in feat_df.columns

    # Check rolling statistics
    for win in [7, 30]:
        assert f"BRENT_CRUDE_ma_{win}" in feat_df.columns
        assert f"BRENT_CRUDE_std_{win}" in feat_df.columns

    # Check ratios
    assert "coal_to_bunker_ratio" in feat_df.columns
    assert "iron_to_bunker_ratio" in feat_df.columns

    # Check seasonal flags
    assert "is_monsoon" in feat_df.columns
    assert "is_winter_heating" in feat_df.columns
    assert set(feat_df["is_monsoon"].unique()).issubset({0, 1})
    assert set(feat_df["is_winter_heating"].unique()).issubset({0, 1})


def test_training_dataset_alignment():
    """Verify feature matrix X and target y alignment for corridor training."""
    fe = FreightFeatureEngineer()
    X, y = fe.build_training_dataset("NEWCASTLE_HALDIA_PANAMAX")

    assert len(X) == len(y)
    assert len(X) >= 12  # At least 1 year of monthly history
    assert not X.isnull().values.any()
    assert not y.isnull().values.any()


def test_forward_inference_matrix():
    """Verify forward feature generation for future voyages."""
    fe = FreightFeatureEngineer()
    fwd = fe.get_forward_inference_matrix(num_voyages=4)

    assert len(fwd) == 4
    assert not fwd.isnull().values.any()
    assert "is_monsoon" in fwd.columns
    assert "is_winter_heating" in fwd.columns


# ======================================================================
# 3. Multi-Quantile LightGBM Regressor Tests
# ======================================================================

def test_quantile_monotonicity():
    """
    CRITICAL: Verify that the multi-quantile models strictly satisfy:
    p10 <= p50 <= p90 across all forecast horizons.
    """
    forecaster = MultiQuantileForecaster()
    res = forecaster.predict_route("NEWCASTLE", "HALDIA", "PANAMAX", num_voyages=4)

    assert isinstance(res, MLForecastResult)
    assert len(res.p10_rates) == 4
    assert len(res.p50_rates) == 4
    assert len(res.p90_rates) == 4

    for i in range(4):
        p10 = res.p10_rates[i]
        p50 = res.p50_rates[i]
        p90 = res.p90_rates[i]
        assert p10 <= p50, f"Violation at voyage {i+1}: p10 ({p10}) > p50 ({p50})"
        assert p50 <= p90, f"Violation at voyage {i+1}: p50 ({p50}) > p90 ({p90})"


def test_model_training_and_serialization():
    """Verify model training and joblib file persistence."""
    forecaster = MultiQuantileForecaster()
    models = forecaster.train_route("TABONEO_VIZAG_SUPRAMAX")

    assert "p10" in models
    assert "p50" in models
    assert "p90" in models

    # Verify disk files exist
    assert os.path.exists(forecaster._get_model_path("TABONEO_VIZAG_SUPRAMAX", "p10"))
    assert os.path.exists(forecaster._get_model_path("TABONEO_VIZAG_SUPRAMAX", "p50"))
    assert os.path.exists(forecaster._get_model_path("TABONEO_VIZAG_SUPRAMAX", "p90"))


# ======================================================================
# 4. Probability Calculation Bounds Tests
# ======================================================================

def test_probability_bounds_and_extremes():
    """Verify that CDF probabilities strictly obey 0% <= P <= 100%."""
    forecaster = MultiQuantileForecaster()

    # Normal case
    prob = forecaster.calculate_breakeven_probability(
        breakeven_rate=20.0,
        mean_spot_rate=22.45,
        volatility_std=5.245,
    )
    assert 0.0 <= prob <= 100.0

    # Extreme low break-even (spot will practically never fall below)
    prob_low = forecaster.calculate_breakeven_probability(
        breakeven_rate=1.0,
        mean_spot_rate=22.45,
        volatility_std=3.0,
    )
    assert prob_low < 1.0

    # Extreme high break-even (spot will almost certainly fall below)
    prob_high = forecaster.calculate_breakeven_probability(
        breakeven_rate=100.0,
        mean_spot_rate=22.45,
        volatility_std=3.0,
    )
    assert prob_high > 99.0


# ======================================================================
# 5. Financial Evaluator ML Integration Tests
# ======================================================================

def test_financial_evaluator_ml_confidence_cone():
    """
    Verify that FinancialEvaluator uses ML quantile predictions and
    generates valid p10 and p90 confidence bands for spot outlay.
    """
    evaluator = FinancialEvaluator()
    origin = get_port("Newcastle")
    destination = get_port("Haldia")
    vessel = get_vessel_class("Panamax")

    result = evaluator.evaluate(
        cargo_tonnage=75000.0,
        origin=origin,
        destination=destination,
        vessel=vessel,
        num_voyages=4,
        cvc_discount_pct=5.0,
        use_ml=True,
    )

    assert result.ml_forecast is not None
    assert result.p10_spot_total_usd > 0
    assert result.p90_spot_total_usd > 0
    # Spot Outlay Confidence Envelope: p10 <= p50 <= p90
    assert result.p10_spot_total_usd <= result.spot_total_usd <= result.p90_spot_total_usd
    assert "CVC saves" in result.headline_summary or "Spot saves" in result.headline_summary


# ======================================================================
# 6. CLI Command Handlers Tests
# ======================================================================

def test_cli_train_ml_handler(capsys):
    """Verify that handle_train_ml executes cleanly without exceptions."""
    cli.handle_train_ml()
    captured = capsys.readouterr()
    assert "TRAINING MULTI-QUANTILE LIGHTGBM MODELS" in captured.out
    assert "successfully trained" in captured.out


def test_cli_update_data_handler(capsys):
    """Verify that handle_update_data executes cleanly without exceptions."""
    cli.handle_update_data()
    captured = capsys.readouterr()
    assert "POLLING LIVE FREIGHT & COMMODITY PROXIES" in captured.out
    assert "Parquet Store Status" in captured.out
