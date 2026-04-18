"""Feature engineering for RUL prediction on industrial sensor data.

Reusable feature transforms for the Gold layer of the Medallion architecture.
All functions operate on pandas DataFrames and return new DataFrames,
preserving the input data.
"""

from __future__ import annotations

import pandas as pd
from loguru import logger


def rolling_sensor_stats(
    df: pd.DataFrame,
    window_sizes: list[int] | None = None,
    sensor_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Compute rolling mean and standard deviation for sensor columns.

    Args:
        df: DataFrame with sensor readings, sorted by unit_id and cycle.
        window_sizes: Rolling window sizes. Defaults to [5, 10, 20].
        sensor_columns: Columns to compute stats for. Defaults to all sensor_* columns.

    Returns:
        DataFrame with original columns plus rolling stat columns.
    """
    if window_sizes is None:
        window_sizes = [5, 10, 20]
    if sensor_columns is None:
        sensor_columns = [c for c in df.columns if c.startswith("sensor_")]

    result = df.copy()

    for window in window_sizes:
        for col in sensor_columns:
            grouped = result.groupby("unit_id")[col]
            result[f"{col}_rolling_mean_{window}"] = grouped.transform(
                lambda x: x.rolling(window=window, min_periods=1).mean()
            )
            result[f"{col}_rolling_std_{window}"] = grouped.transform(
                lambda x: x.rolling(window=window, min_periods=1).std().fillna(0)
            )

    new_cols = len(result.columns) - len(df.columns)
    logger.info(f"Rolling stats: {new_cols} new features (windows={window_sizes})")
    return result


def compute_rul_labels(
    df: pd.DataFrame,
    max_rul_cap: int = 125,
    unit_col: str = "unit_id",
    cycle_col: str = "cycle",
) -> pd.DataFrame:
    """Compute Remaining Useful Life labels for each reading.

    RUL = max_cycle_for_unit - current_cycle, capped at max_rul_cap.
    Capping prevents the model from learning irrelevant early-life patterns.

    Args:
        df: DataFrame with unit_id and cycle columns.
        max_rul_cap: Upper cap for RUL values.
        unit_col: Column name for unit identifier.
        cycle_col: Column name for cycle number.

    Returns:
        DataFrame with added 'rul' column.
    """
    result = df.copy()
    max_cycles = result.groupby(unit_col)[cycle_col].transform("max")
    result["rul"] = max_cycles - result[cycle_col]
    result["rul"] = result["rul"].clip(upper=max_rul_cap)

    logger.info(
        f"RUL labels computed: range [{result['rul'].min()}, {result['rul'].max()}], "
        f"cap={max_rul_cap}"
    )
    return result


def create_lag_features(
    df: pd.DataFrame,
    lags: list[int] | None = None,
    sensor_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Create lagged sensor features within each unit's time series.

    Args:
        df: DataFrame with sensor readings, sorted by unit_id and cycle.
        lags: Lag periods to create. Defaults to [1, 5, 10].
        sensor_columns: Columns to lag. Defaults to all sensor_* columns.

    Returns:
        DataFrame with original columns plus lag feature columns.
    """
    if lags is None:
        lags = [1, 5, 10]
    if sensor_columns is None:
        sensor_columns = [c for c in df.columns if c.startswith("sensor_")]

    result = df.copy()

    for lag in lags:
        for col in sensor_columns:
            result[f"{col}_lag_{lag}"] = result.groupby("unit_id")[col].shift(lag)

    new_cols = len(result.columns) - len(df.columns)
    logger.info(f"Lag features: {new_cols} new features (lags={lags})")
    return result


def create_rate_of_change_features(
    df: pd.DataFrame,
    sensor_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Compute cycle-over-cycle rate of change for sensor readings.

    Args:
        df: DataFrame with sensor readings, sorted by unit_id and cycle.
        sensor_columns: Columns to differentiate. Defaults to all sensor_* columns.

    Returns:
        DataFrame with added rate-of-change columns.
    """
    if sensor_columns is None:
        sensor_columns = [c for c in df.columns if c.startswith("sensor_")]

    result = df.copy()

    for col in sensor_columns:
        result[f"{col}_roc"] = result.groupby("unit_id")[col].diff()

    logger.info(f"Rate-of-change features: {len(sensor_columns)} new columns")
    return result


def build_feature_set(
    df: pd.DataFrame,
    window_sizes: list[int] | None = None,
    lags: list[int] | None = None,
    max_rul_cap: int = 125,
) -> pd.DataFrame:
    """Build the complete ML-ready feature set.

    Applies rolling stats, lag features, rate of change, and RUL labels
    in the correct order.

    Args:
        df: Raw sensor DataFrame with unit_id and cycle columns.
        window_sizes: Rolling window sizes.
        lags: Lag periods.
        max_rul_cap: RUL cap value.

    Returns:
        ML-ready DataFrame with all engineered features and RUL labels.
    """
    logger.info(f"Building feature set from {len(df)} records")

    result = df.sort_values(["unit_id", "cycle"]).reset_index(drop=True)
    result = rolling_sensor_stats(result, window_sizes)
    result = create_lag_features(result, lags)
    result = create_rate_of_change_features(result)
    result = compute_rul_labels(result, max_rul_cap)

    result = result.dropna()

    logger.info(
        f"Feature set complete: {result.shape[0]} records, "
        f"{result.shape[1]} columns (after dropping NaN rows)"
    )
    return result
