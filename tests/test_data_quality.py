"""Tests for the data quality module."""

import pandas as pd
import pytest

from src.data_quality import (
    operational_mode_validation,
    reading_frequency_compliance,
    sensor_drift_detection,
)


@pytest.fixture
def sensor_df_with_known_drift() -> pd.DataFrame:
    """30 readings where the last value is an extreme outlier."""
    values = [100.0] * 29 + [999.0]
    return pd.DataFrame({
        "unit_id": [1] * 30,
        "cycle": list(range(1, 31)),
        "s1": values,
        "s2": [200.0] * 30,
    })


@pytest.fixture
def complete_df() -> pd.DataFrame:
    """10 cycles with no gaps for a single unit."""
    return pd.DataFrame({
        "unit_id": [1] * 10,
        "cycle": list(range(1, 11)),
        "s1": [100.0] * 10,
    })


@pytest.fixture
def gapped_df() -> pd.DataFrame:
    """Two units with missing cycles."""
    return pd.DataFrame({
        "unit_id": [1, 1, 1, 1, 2, 2, 2],
        "cycle": [1, 2, 5, 6, 1, 3, 4],
        "s1": [100.0] * 7,
    })


class TestSensorDriftDetection:
    def test_flags_known_drift(self, sensor_df_with_known_drift: pd.DataFrame) -> None:
        """A 10x spike in the last reading should be flagged as drift."""
        result_df, report = sensor_drift_detection(
            sensor_df_with_known_drift,
            sensor_cols=["s1"],
            window=20,
            z_threshold=3.0,
        )
        assert result_df["drift_flag"].iloc[-1], "Last row should be flagged as drifted"
        assert report["records_flagged"] >= 1
        assert report["per_sensor_drift_count"]["s1"] >= 1

    def test_stable_sensor_not_flagged(self, sensor_df_with_known_drift: pd.DataFrame) -> None:
        """A constant-value sensor (s2) in the same DataFrame should have 0 drift."""
        _, report = sensor_drift_detection(
            sensor_df_with_known_drift,
            sensor_cols=["s2"],
            window=20,
            z_threshold=3.0,
        )
        assert report["per_sensor_drift_count"]["s2"] == 0

    def test_report_structure(self, sensor_df_with_known_drift: pd.DataFrame) -> None:
        """Report should contain all required keys."""
        _, report = sensor_drift_detection(
            sensor_df_with_known_drift,
            sensor_cols=["s1"],
        )
        required_keys = {"check", "total_records", "records_flagged", "flag_rate", "per_sensor_drift_count"}
        assert required_keys.issubset(report.keys())

    def test_flag_rate_calculation(self, complete_df: pd.DataFrame) -> None:
        """Flag rate should be 0.0 for perfectly stable data."""
        _, report = sensor_drift_detection(complete_df, sensor_cols=["s1"])
        assert report["flag_rate"] == 0.0


class TestReadingFrequencyCompliance:
    def test_perfect_score(self, complete_df: pd.DataFrame) -> None:
        """Complete sequential data should yield quality_score=1.0."""
        _, report = reading_frequency_compliance(complete_df)
        assert report["quality_score"] == 1.0
        assert report["total_missing_cycles"] == 0
        assert report["duplicate_count"] == 0

    def test_gaps_lower_score(self, gapped_df: pd.DataFrame) -> None:
        """Missing cycles should reduce quality_score below 1.0."""
        _, report = reading_frequency_compliance(gapped_df)
        assert report["quality_score"] < 1.0
        assert report["total_missing_cycles"] > 0
        assert 1 in report["missing_cycles_per_unit"]
        assert 3 in report["missing_cycles_per_unit"][1]

    def test_duplicates_detected(self) -> None:
        """Duplicate (unit_id, cycle) pairs should be counted."""
        dup_df = pd.DataFrame({
            "unit_id": [1, 1, 1],
            "cycle": [1, 1, 2],
            "s1": [100.0, 100.0, 100.0],
        })
        _, report = reading_frequency_compliance(dup_df)
        assert report["duplicate_count"] == 1


class TestOperationalModeValidation:
    def test_flags_out_of_envelope(self) -> None:
        """Settings outside bounds should be flagged."""
        df = pd.DataFrame({
            "unit_id": [1, 1],
            "cycle": [1, 2],
            "op_setting_1": [0.0, 999.0],
            "op_setting_2": [0.0, 0.0],
            "op_setting_3": [100.0, 100.0],
        })
        result_df, report = operational_mode_validation(df)
        assert result_df["op_mode_flag"].iloc[1]
        assert report["records_flagged"] == 1
