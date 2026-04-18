"""Data quality validation for industrial sensor telemetry.

Implements sensor drift detection, reading frequency compliance, and
operational mode validation for the Silver layer of the Medallion
architecture. Each check returns a (cleaned_df, quality_report) tuple
to support both pipeline filtering and observability.

Pandas only — designed for local development and Databricks driver-side
execution. For PySpark equivalents, see notebooks/02_silver_transformations.py.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

QualityReport = dict[str, Any]

SENSOR_RANGE_BOUNDS: dict[str, tuple[float, float]] = {
    "s2": (640.0, 645.0),
    "s3": (1570.0, 1620.0),
    "s4": (1380.0, 1420.0),
    "s7": (549.0, 556.0),
    "s8": (2387.0, 2389.0),
    "s9": (9040.0, 9110.0),
    "s11": (47.0, 49.0),
    "s12": (520.0, 525.0),
    "s13": (2387.0, 2389.0),
    "s14": (8125.0, 8155.0),
    "s15": (8.4, 8.8),
    "s17": (392.0, 400.0),
    "s20": (38.5, 39.5),
    "s21": (23.2, 23.6),
}

OPERATIONAL_SETTING_BOUNDS: dict[str, tuple[float, float]] = {
    "op_setting_1": (-0.0087, 0.0087),
    "op_setting_2": (-0.0007, 0.0007),
    "op_setting_3": (99.0, 101.0),
}


def sensor_drift_detection(
    df: pd.DataFrame,
    sensor_cols: list[str] | None = None,
    window: int = 20,
    z_threshold: float = 3.0,
) -> tuple[pd.DataFrame, QualityReport]:
    """Detect sensor drift using per-unit rolling z-score analysis.

    For each sensor, computes a rolling mean and std within each unit's
    time series. Readings whose absolute z-score exceeds the threshold
    are flagged. A composite ``drift_flag`` column is added — True if
    *any* sensor drifted for that reading.

    Args:
        df: DataFrame with sensor readings. Must contain ``unit_id`` and
            ``cycle`` columns, plus the sensor columns to check.
        sensor_cols: Sensor columns to evaluate. Defaults to all columns
            matching the pattern ``s\\d+``.
        window: Rolling window size for computing baseline statistics.
            Larger windows are more robust but slower to react.
        z_threshold: Absolute z-score above which a reading is flagged
            as drifted. 3.0 ≈ 0.3% false positive rate for normal data.

    Returns:
        Tuple of (flagged_df, quality_report).
        - flagged_df: Copy of input with ``drift_flag`` bool column added.
        - quality_report: Dict with keys ``total_records``,
          ``records_flagged``, ``flag_rate``, ``per_sensor_drift_count``.
    """
    if sensor_cols is None:
        sensor_cols = sorted([c for c in df.columns if c.startswith("s") and c[1:].isdigit()])

    if not sensor_cols:
        raise ValueError("No sensor columns found. Pass sensor_cols explicitly.")

    result = df.copy()
    per_sensor_drift: dict[str, int] = {}

    for col in sensor_cols:
        grouped = result.groupby("unit_id")[col]
        rolling_mean = grouped.transform(
            lambda x: x.rolling(window=window, min_periods=1).mean()
        )
        rolling_std = grouped.transform(
            lambda x: x.rolling(window=window, min_periods=1).std()
        )
        rolling_std = rolling_std.fillna(0).replace(0, 1e-8)

        z_scores = ((result[col] - rolling_mean) / rolling_std).abs()
        flag_col = f"_drift_{col}"
        result[flag_col] = z_scores > z_threshold
        drift_count = int(result[flag_col].sum())
        per_sensor_drift[col] = drift_count

        if drift_count > 0:
            logger.warning(
                "Drift detected in {col}: {count} readings above z={z:.1f}",
                col=col,
                count=drift_count,
                z=z_threshold,
            )

    drift_cols = [c for c in result.columns if c.startswith("_drift_")]
    result["drift_flag"] = result[drift_cols].any(axis=1)
    result = result.drop(columns=drift_cols)

    records_flagged = int(result["drift_flag"].sum())
    report: QualityReport = {
        "check": "sensor_drift_detection",
        "total_records": len(result),
        "records_flagged": records_flagged,
        "flag_rate": round(records_flagged / max(len(result), 1), 4),
        "per_sensor_drift_count": per_sensor_drift,
        "window": window,
        "z_threshold": z_threshold,
    }

    logger.info(
        "Drift check complete: {flagged}/{total} flagged ({rate:.2%})",
        flagged=records_flagged,
        total=len(result),
        rate=report["flag_rate"],
    )
    return result, report


def reading_frequency_compliance(
    df: pd.DataFrame,
    expected_interval_sec: float = 1.0,
    unit_col: str = "unit_id",
    cycle_col: str = "cycle",
) -> tuple[pd.DataFrame, QualityReport]:
    """Evaluate reading frequency compliance per unit.

    For C-MAPSS data, each unit should have exactly one reading per cycle
    with no gaps. This function checks for missing cycles and duplicate
    readings, returning a quality score from 0.0 (fully non-compliant)
    to 1.0 (perfect).

    Args:
        df: DataFrame with unit and cycle columns.
        expected_interval_sec: Expected time between readings in seconds.
            Used for reporting context; the actual check is cycle-gap based.
        unit_col: Column name for the equipment unit identifier.
        cycle_col: Column name for the cycle/timestamp ordinal.

    Returns:
        Tuple of (df, quality_report).
        - df: Input DataFrame unchanged (frequency is a dataset-level check).
        - quality_report: Dict with ``quality_score`` (0–1),
          ``total_records``, ``records_flagged``, ``flag_rate``,
          ``missing_cycles_per_unit``, ``duplicate_count``.
    """
    total_expected = 0
    total_actual = 0
    total_missing = 0
    missing_per_unit: dict[int, list[int]] = {}

    for unit_id, group in df.groupby(unit_col):
        cycles = group[cycle_col].sort_values()
        cycle_min, cycle_max = int(cycles.min()), int(cycles.max())
        expected_set = set(range(cycle_min, cycle_max + 1))
        actual_set = set(cycles.astype(int))
        missing = sorted(expected_set - actual_set)

        total_expected += len(expected_set)
        total_actual += len(actual_set)

        if missing:
            missing_per_unit[int(unit_id)] = missing
            total_missing += len(missing)
            logger.warning(
                "Unit {uid}: {n} missing cycles (e.g. {sample})",
                uid=unit_id,
                n=len(missing),
                sample=missing[:5],
            )

    duplicate_count = int(df.duplicated(subset=[unit_col, cycle_col]).sum())
    if duplicate_count > 0:
        logger.warning("{n} duplicate (unit_id, cycle) pairs found", n=duplicate_count)

    records_flagged = total_missing + duplicate_count
    quality_score = round(1.0 - (records_flagged / max(total_expected, 1)), 4)

    report: QualityReport = {
        "check": "reading_frequency_compliance",
        "total_records": len(df),
        "records_flagged": records_flagged,
        "flag_rate": round(records_flagged / max(len(df), 1), 4),
        "quality_score": quality_score,
        "expected_interval_sec": expected_interval_sec,
        "missing_cycles_per_unit": missing_per_unit,
        "duplicate_count": duplicate_count,
        "total_missing_cycles": total_missing,
    }

    logger.info(
        "Frequency compliance: score={score:.4f}, {missing} missing cycles, "
        "{dupes} duplicates across {units} units",
        score=quality_score,
        missing=total_missing,
        dupes=duplicate_count,
        units=df[unit_col].nunique(),
    )
    return df, report


def operational_mode_validation(
    df: pd.DataFrame,
    op_setting_cols: list[str] | None = None,
    bounds: dict[str, tuple[float, float]] | None = None,
) -> tuple[pd.DataFrame, QualityReport]:
    """Flag records outside the expected operational envelope.

    FD001 operates under a single fault mode and operating condition, so
    operational settings should remain near-constant. Records with any
    setting outside the configured bounds are flagged.

    Args:
        df: DataFrame with operational setting columns.
        op_setting_cols: Setting columns to validate. Defaults to
            ``["op_setting_1", "op_setting_2", "op_setting_3"]``.
        bounds: Dict of ``{column: (lower, upper)}`` defining the
            acceptable envelope. Defaults to OPERATIONAL_SETTING_BOUNDS.

    Returns:
        Tuple of (flagged_df, quality_report).
        - flagged_df: Copy of input with ``op_mode_flag`` bool column.
        - quality_report: Dict with ``total_records``, ``records_flagged``,
          ``flag_rate``, ``per_setting_violation_count``.
    """
    if op_setting_cols is None:
        op_setting_cols = ["op_setting_1", "op_setting_2", "op_setting_3"]
    if bounds is None:
        bounds = OPERATIONAL_SETTING_BOUNDS

    result = df.copy()
    per_setting_violations: dict[str, int] = {}

    for col in op_setting_cols:
        if col not in result.columns:
            logger.warning("Column {col} not found in DataFrame — skipping", col=col)
            continue

        lower, upper = bounds.get(col, (-np.inf, np.inf))
        flag_col = f"_oor_{col}"
        result[flag_col] = (result[col] < lower) | (result[col] > upper)
        violation_count = int(result[flag_col].sum())
        per_setting_violations[col] = violation_count

        if violation_count > 0:
            logger.warning(
                "{col}: {n} readings outside envelope [{lo}, {hi}]",
                col=col,
                n=violation_count,
                lo=lower,
                hi=upper,
            )

    oor_cols = [c for c in result.columns if c.startswith("_oor_")]
    result["op_mode_flag"] = result[oor_cols].any(axis=1) if oor_cols else False
    result = result.drop(columns=oor_cols)

    records_flagged = int(result["op_mode_flag"].sum())
    report: QualityReport = {
        "check": "operational_mode_validation",
        "total_records": len(result),
        "records_flagged": records_flagged,
        "flag_rate": round(records_flagged / max(len(result), 1), 4),
        "per_setting_violation_count": per_setting_violations,
    }

    logger.info(
        "Op-mode validation: {flagged}/{total} flagged ({rate:.2%})",
        flagged=records_flagged,
        total=len(result),
        rate=report["flag_rate"],
    )
    return result, report


def run_all_checks(
    df: pd.DataFrame,
    sensor_cols: list[str] | None = None,
    op_setting_cols: list[str] | None = None,
    drift_window: int = 20,
    drift_z_threshold: float = 3.0,
) -> tuple[pd.DataFrame, QualityReport]:
    """Execute all data quality checks and return a consolidated result.

    Runs sensor drift detection, reading frequency compliance, and
    operational mode validation in sequence. Flag columns from each
    check are preserved in the output DataFrame.

    Args:
        df: Raw sensor DataFrame to validate.
        sensor_cols: Sensor columns for drift detection.
        op_setting_cols: Operational setting columns for mode validation.
        drift_window: Rolling window for drift detection.
        drift_z_threshold: Z-score threshold for drift flagging.

    Returns:
        Tuple of (flagged_df, consolidated_report).
        - flagged_df: DataFrame with ``drift_flag`` and ``op_mode_flag`` columns.
        - consolidated_report: Dict with per-check reports and aggregate stats.
    """
    logger.info("Running all quality checks on {n} records", n=len(df))

    result, drift_report = sensor_drift_detection(
        df, sensor_cols, window=drift_window, z_threshold=drift_z_threshold
    )
    _, freq_report = reading_frequency_compliance(result)
    result, op_report = operational_mode_validation(result, op_setting_cols)

    any_flag = result["drift_flag"] | result["op_mode_flag"]
    total_flagged = int(any_flag.sum())

    consolidated: QualityReport = {
        "total_records": len(result),
        "records_flagged": total_flagged,
        "flag_rate": round(total_flagged / max(len(result), 1), 4),
        "checks": {
            "sensor_drift": drift_report,
            "reading_frequency": freq_report,
            "operational_mode": op_report,
        },
    }

    logger.info(
        "All checks complete: {flagged}/{total} records flagged ({rate:.2%})",
        flagged=total_flagged,
        total=len(result),
        rate=consolidated["flag_rate"],
    )
    return result, consolidated
