"""Tests for the data quality module."""

import pandas as pd
import pytest

from src.data_quality import check_reading_frequency, detect_sensor_drift


@pytest.fixture
def sensor_df_with_drift() -> pd.DataFrame:
    """Create a DataFrame where the last reading has an extreme value."""
    normal_values = [100.0] * 30
    normal_values[-1] = 999.0  # inject a spike
    return pd.DataFrame({
        "unit_id": [1] * 30,
        "cycle": list(range(1, 31)),
        "sensor_1": normal_values,
    })


@pytest.fixture
def sensor_df_with_gaps() -> pd.DataFrame:
    """Create a DataFrame with missing cycles."""
    return pd.DataFrame({
        "unit_id": [1, 1, 1, 1, 2, 2, 2],
        "cycle": [1, 2, 5, 6, 1, 3, 4],  # unit 1 missing 3,4; unit 2 missing 2
        "sensor_1": [100.0] * 7,
    })


class TestDetectSensorDrift:
    def test_drift_detected_on_spike(self, sensor_df_with_drift: pd.DataFrame) -> None:
        """An extreme outlier should be flagged as drift."""
        flags = detect_sensor_drift(
            sensor_df_with_drift,
            sensor_columns=["sensor_1"],
            window=20,
            z_threshold=3.0,
        )
        assert flags["sensor_1"].iloc[-1] is True or flags["sensor_1"].iloc[-1] == True  # noqa: E712

    def test_no_drift_on_stable_data(self) -> None:
        """Constant-value sensor data should produce no drift flags."""
        stable_df = pd.DataFrame({
            "unit_id": [1] * 50,
            "cycle": list(range(1, 51)),
            "sensor_1": [100.0] * 50,
        })
        flags = detect_sensor_drift(stable_df, sensor_columns=["sensor_1"])
        assert not flags["sensor_1"].any()


class TestCheckReadingFrequency:
    def test_gaps_detected(self, sensor_df_with_gaps: pd.DataFrame) -> None:
        """Missing cycles should be reported per unit."""
        gaps = check_reading_frequency(sensor_df_with_gaps)
        assert 1 in gaps
        assert 3 in gaps[1]
        assert 4 in gaps[1]
        assert 2 in gaps
        assert 2 in gaps[2]

    def test_no_gaps_on_complete_data(self) -> None:
        """Complete sequential data should return no gaps."""
        complete_df = pd.DataFrame({
            "unit_id": [1] * 10,
            "cycle": list(range(1, 11)),
            "sensor_1": [100.0] * 10,
        })
        gaps = check_reading_frequency(complete_df)
        assert len(gaps) == 0
