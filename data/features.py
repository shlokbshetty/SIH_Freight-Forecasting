"""
Maritime Feature Engineering Pipeline.
Transforms raw time-series into model-ready features with lags, rolling moving averages,
volatility estimators, commodity-to-fuel ratios, and seasonal Indian monsoon indicators.
"""

from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from data.fetcher import MarketDataFetcher


class FreightFeatureEngineer:
    """
    Transforms macro proxy and corridor time-series into ML-ready tabular features.
    """

    CORE_COLUMNS = [
        "GOGL",
        "SBLK",
        "ZIM",
        "COAL_NEWCASTLE",
        "IRON_ORE",
        "BRENT_CRUDE",
        "USD_INR",
        "USD_AUD",
    ]

    LAG_DAYS = [1, 7, 14, 30]
    ROLLING_WINDOWS = [7, 30]

    def __init__(self, fetcher: Optional[MarketDataFetcher] = None):
        self.fetcher = fetcher or MarketDataFetcher()

    def engineer_macro_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Takes raw daily macro dataframe and computes:
        - Multi-horizon lags: t-1, t-7, t-14, t-30
        - Moving averages and rolling standard deviations: 7-day and 30-day
        - Commodity-to-bunker fuel spreads
        - Seasonal indicators (Month, Quarter, Indian Monsoon, Winter heating peak)
        """
        data = df.copy()
        data["date"] = pd.to_datetime(data["date"])
        data.sort_values("date", inplace=True)
        data.reset_index(drop=True, inplace=True)

        feature_df = pd.DataFrame({"date": data["date"]})

        # 1. Base values, lags, and rolling statistics
        for col in self.CORE_COLUMNS:
            if col in data.columns:
                series = data[col]
                feature_df[col] = series

                # Lags
                for lag in self.LAG_DAYS:
                    feature_df[f"{col}_lag_{lag}"] = series.shift(lag)

                # Rolling Moving Averages and Volatility
                for win in self.ROLLING_WINDOWS:
                    feature_df[f"{col}_ma_{win}"] = series.rolling(window=win, min_periods=1).mean()
                    feature_df[f"{col}_std_{win}"] = series.rolling(window=win, min_periods=1).std().fillna(0.0)

        # 2. Domain ratios and shipping momentum
        if "COAL_NEWCASTLE" in data.columns and "BRENT_CRUDE" in data.columns:
            feature_df["coal_to_bunker_ratio"] = data["COAL_NEWCASTLE"] / np.maximum(1.0, data["BRENT_CRUDE"])
        if "IRON_ORE" in data.columns and "BRENT_CRUDE" in data.columns:
            feature_df["iron_to_bunker_ratio"] = data["IRON_ORE"] / np.maximum(1.0, data["BRENT_CRUDE"])
        if "GOGL" in feature_df.columns and "GOGL_ma_30" in feature_df.columns:
            feature_df["gogl_momentum_30"] = feature_df["GOGL"] / np.maximum(0.1, feature_df["GOGL_ma_30"])

        # 3. Seasonal & Calendar Indicators
        dates = feature_df["date"]
        feature_df["month"] = dates.dt.month
        feature_df["quarter"] = dates.dt.quarter
        # Indian Monsoon Season (June - September: rough seas, tidal river siltation at Haldia)
        feature_df["is_monsoon"] = dates.dt.month.isin([6, 7, 8, 9]).astype(int)
        # North Asia Winter Peak (November - February: heavy thermal coal procurement)
        feature_df["is_winter_heating"] = dates.dt.month.isin([11, 12, 1, 2]).astype(int)

        # Drop initial rows with NaN from 30-day shift
        feature_df.dropna(inplace=True)
        feature_df.reset_index(drop=True, inplace=True)

        return feature_df

    def build_training_dataset(
        self, route_col: str
    ) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Builds aligned (X, y) training dataset for a specific route corridor.
        Resamples daily engineered features to monthly intervals to align with
        monthly corridor freight rate fixtures.
        """
        macro_raw = self.fetcher.load_macro_data()
        macro_feat = self.engineer_macro_features(macro_raw)

        # Aggregate features to monthly (mean of the month)
        macro_feat.set_index("date", inplace=True)
        macro_monthly = macro_feat.resample("MS").mean().reset_index()

        route_raw = self.fetcher.load_route_data()
        route_raw["date"] = pd.to_datetime(route_raw["date"])

        if route_col not in route_raw.columns:
            raise KeyError(
                f"Route '{route_col}' not found in route fixtures. Available: {list(route_raw.columns)}"
            )

        # Merge on monthly date
        merged = pd.merge(
            macro_monthly,
            route_raw[["date", route_col]],
            on="date",
            how="inner",
        )

        merged.dropna(inplace=True)
        merged.sort_values("date", inplace=True)

        # Features X and Target y
        feature_cols = [c for c in merged.columns if c not in ["date", route_col]]
        X = merged[feature_cols]
        y = merged[route_col]

        return X, y

    def get_forward_inference_matrix(
        self,
        num_voyages: int = 4,
        start_month_offset: int = 1,
    ) -> pd.DataFrame:
        """
        Generates feature vectors for future N voyages by rolling forward the latest
        known macro indicators and applying seasonal indicators for future months.
        """
        macro_raw = self.fetcher.load_macro_data()
        macro_feat = self.engineer_macro_features(macro_raw)

        # Take the most recent feature vector as baseline
        latest_row = macro_feat.iloc[-1].copy()
        last_date = pd.to_datetime(latest_row["date"])

        feature_cols = [c for c in macro_feat.columns if c != "date"]
        forward_rows = []

        for v in range(1, num_voyages + 1):
            future_date = last_date + pd.DateOffset(months=v)
            row_dict = latest_row[feature_cols].to_dict()

            # Update calendar/seasonal features for the future month
            m = future_date.month
            q = (m - 1) // 3 + 1
            row_dict["month"] = m
            row_dict["quarter"] = q
            row_dict["is_monsoon"] = 1 if m in [6, 7, 8, 9] else 0
            row_dict["is_winter_heating"] = 1 if m in [11, 12, 1, 2] else 0

            forward_rows.append(row_dict)

        return pd.DataFrame(forward_rows)
