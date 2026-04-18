"""Tests for the feature engineering module."""

import pandas as pd
import pytest

from src.feature_engineering import (
    compute_rul_labels,
    create_lag_features,
    rolling_sensor_stats,
)


@pytest.fixture
def sample_sensor_df() -> pd.DataFrame:
    """Create a minimal sensor DataFrame for testing."""
    return pd.DataFrame({
        "unit_id": [1] * 10 + [2] * 10,
        "cycle": list(range(1, 11)) * 2,
        "sensor_1": list(range(100, 120)),
        "sensor_2": list(range(200, 220)),
    })


class TestComputeRulLabels:
    def test_rul_values_correct(self, sample_sensor_df: pd.DataFrame) -> None:
        """RUL should equal max_cycle - current_cycle per unit."""
        result = compute_rul_labels(sample_sensor_df, max_rul_cap=999)
        unit_1 = result[result["unit_id"] == 1]
        assert unit_1.iloc[0]["rul"] == 9  # cycle 1: max(10) - 1 = 9
        assert unit_1.iloc[-1]["rul"] == 0  # cycle 10: max(10) - 10 = 0

    def test_rul_cap_applied(self, sample_sensor_df: pd.DataFrame) -> None:
        """RUL values above the cap should be clipped."""
        result = compute_rul_labels(sample_sensor_df, max_rul_cap=5)
        assert result["rul"].max() == 5

    def test_original_df_not_modified(self, sample_sensor_df: pd.DataFrame) -> None:
        """Input DataFrame should not be mutated."""
        original_cols = set(sample_sensor_df.columns)
        compute_rul_labels(sample_sensor_df)
        assert set(sample_sensor_df.columns) == original_cols


class TestRollingSensorStats:
    def test_new_columns_created(self, sample_sensor_df: pd.DataFrame) -> None:
        """Rolling stats should add mean and std columns for each window size."""
        result = rolling_sensor_stats(sample_sensor_df, window_sizes=[3])
        assert "sensor_1_rolling_mean_3" in result.columns
        assert "sensor_1_rolling_std_3" in result.columns

    def test_multiple_windows(self, sample_sensor_df: pd.DataFrame) -> None:
        """Each window size should produce its own set of columns."""
        result = rolling_sensor_stats(sample_sensor_df, window_sizes=[3, 5])
        expected_new = 2 * 2 * 2  # 2 sensors × 2 stats × 2 windows
        assert len(result.columns) == len(sample_sensor_df.columns) + expected_new


class TestCreateLagFeatures:
    def test_lag_columns_created(self, sample_sensor_df: pd.DataFrame) -> None:
        """Lag features should create one column per sensor per lag."""
        result = create_lag_features(sample_sensor_df, lags=[1, 2])
        assert "sensor_1_lag_1" in result.columns
        assert "sensor_2_lag_2" in result.columns

    def test_lag_values_correct(self, sample_sensor_df: pd.DataFrame) -> None:
        """Lag-1 of sensor_1 for unit 1 should shift values by one position."""
        result = create_lag_features(sample_sensor_df, lags=[1])
        unit_1 = result[result["unit_id"] == 1].reset_index(drop=True)
        assert pd.isna(unit_1.loc[0, "sensor_1_lag_1"])
        assert unit_1.loc[1, "sensor_1_lag_1"] == unit_1.loc[0, "sensor_1"]
