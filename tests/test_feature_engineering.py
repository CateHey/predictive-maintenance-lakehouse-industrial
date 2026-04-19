"""Tests for the feature engineering module."""

import numpy as np
import pandas as pd
import pytest

from src.feature_engineering import (
    compute_rul_labels,
    create_lag_features,
    rolling_sensor_stats,
)


@pytest.fixture
def sample_sensor_df() -> pd.DataFrame:
    """Two units, 10 cycles each, 2 sensors."""
    return pd.DataFrame({
        "unit_id": [1] * 10 + [2] * 10,
        "cycle": list(range(1, 11)) * 2,
        "s1": list(range(100, 120)),
        "s2": list(range(200, 220)),
    })


@pytest.fixture
def multi_unit_df() -> pd.DataFrame:
    """Three units with different lifespans for boundary testing."""
    return pd.DataFrame({
        "unit_id": [1] * 5 + [2] * 8 + [3] * 3,
        "cycle": list(range(1, 6)) + list(range(1, 9)) + list(range(1, 4)),
        "s1": np.random.default_rng(42).normal(500, 10, 16).tolist(),
        "s2": np.random.default_rng(99).normal(640, 2, 16).tolist(),
    })


class TestRollingSensorStats:
    def test_adds_correct_columns(self, sample_sensor_df: pd.DataFrame) -> None:
        """Should add mean, std, min, max, range for each sensor x window."""
        result = rolling_sensor_stats(sample_sensor_df, window_sizes=[3])
        for stat in ("mean", "std", "min", "max", "range"):
            assert f"s1_rolling_{stat}_3" in result.columns
            assert f"s2_rolling_{stat}_3" in result.columns

    def test_column_count_formula(self, sample_sensor_df: pd.DataFrame) -> None:
        """New columns = sensors * windows * 5 stats."""
        result = rolling_sensor_stats(sample_sensor_df, window_sizes=[5, 10])
        expected_new = 2 * 2 * 5  # 2 sensors x 2 windows x 5 stats
        assert len(result.columns) == len(sample_sensor_df.columns) + expected_new

    def test_does_not_mutate_input(self, sample_sensor_df: pd.DataFrame) -> None:
        """Original DataFrame should be unchanged."""
        original_cols = list(sample_sensor_df.columns)
        rolling_sensor_stats(sample_sensor_df, window_sizes=[3])
        assert list(sample_sensor_df.columns) == original_cols


class TestComputeRulLabels:
    def test_caps_at_max(self, sample_sensor_df: pd.DataFrame) -> None:
        """RUL should never exceed max_rul_cap."""
        result = compute_rul_labels(sample_sensor_df, max_rul_cap=5)
        assert result["rul"].max() == 5

    def test_rul_zero_at_failure(self, sample_sensor_df: pd.DataFrame) -> None:
        """Last cycle of each unit should have RUL=0."""
        result = compute_rul_labels(sample_sensor_df, max_rul_cap=999)
        for uid in result["unit_id"].unique():
            unit = result[result["unit_id"] == uid]
            last_row = unit[unit["cycle"] == unit["cycle"].max()]
            assert last_row["rul"].iloc[0] == 0

    def test_piecewise_linear_shape(self, sample_sensor_df: pd.DataFrame) -> None:
        """With cap=5 and 10 cycles, first 5 should be capped, last 5 linear."""
        result = compute_rul_labels(sample_sensor_df, max_rul_cap=5)
        unit_1 = result[result["unit_id"] == 1].sort_values("cycle")
        ruls = unit_1["rul"].tolist()
        assert ruls[:5] == [5, 5, 5, 5, 5]
        assert ruls[5:] == [4, 3, 2, 1, 0]


class TestCreateLagFeatures:
    def test_handles_unit_boundaries(self, multi_unit_df: pd.DataFrame) -> None:
        """Lag features must not leak across unit boundaries.

        The first row of each unit should have NaN for lag-1,
        not a value from the previous unit's last row.
        """
        result = create_lag_features(multi_unit_df, lags=[1])

        for uid in result["unit_id"].unique():
            unit = result[result["unit_id"] == uid].sort_values("cycle")
            assert pd.isna(unit.iloc[0]["s1_lag_1"]), (
                f"Unit {uid}: first row lag should be NaN, got {unit.iloc[0]['s1_lag_1']}"
            )

    def test_lag_values_shift_correctly(self, sample_sensor_df: pd.DataFrame) -> None:
        """Lag-1 should equal the previous cycle's value within the same unit."""
        result = create_lag_features(sample_sensor_df, lags=[1])
        unit_1 = result[result["unit_id"] == 1].sort_values("cycle").reset_index(drop=True)
        assert pd.isna(unit_1.loc[0, "s1_lag_1"])
        assert unit_1.loc[1, "s1_lag_1"] == unit_1.loc[0, "s1"]
        assert unit_1.loc[5, "s1_lag_1"] == unit_1.loc[4, "s1"]

    def test_larger_lag_produces_more_nans(self, sample_sensor_df: pd.DataFrame) -> None:
        """Lag-5 should produce 5 NaN rows at the start of each unit."""
        result = create_lag_features(sample_sensor_df, lags=[5])
        for uid in result["unit_id"].unique():
            unit = result[result["unit_id"] == uid].sort_values("cycle")
            nan_count = unit["s1_lag_5"].isna().sum()
            assert nan_count == 5
