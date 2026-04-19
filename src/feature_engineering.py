"""Feature engineering for RUL prediction on industrial sensor data.

Reusable feature transforms for the Gold layer of the Medallion architecture.
All functions operate on pandas DataFrames, return new DataFrames without
mutating the input, and are designed for single-node execution.

For PySpark equivalents, see notebooks/03_gold_feature_engineering.py.
"""

from __future__ import annotations

import pandas as pd
from loguru import logger


def rolling_sensor_stats(
    df: pd.DataFrame,
    sensor_cols: list[str] | None = None,
    window_sizes: list[int] | None = None,
) -> pd.DataFrame:
    """Compute rolling descriptive statistics for sensor columns.

    For each sensor and window size, adds five new columns:
    ``{sensor}_rolling_{stat}_{window}`` where stat is one of
    mean, std, min, max, range. All rolling computations are
    partitioned by ``unit_id`` to prevent cross-unit contamination.

    Args:
        df: DataFrame with sensor readings. Must contain a ``unit_id``
            column and be sorted by ``unit_id`` and ``cycle``.
        sensor_cols: Sensor columns to compute stats for. Defaults to
            all columns matching the pattern ``s\\d+``.
        window_sizes: Rolling window sizes in cycles. Defaults to
            ``[5, 10, 20]``. Larger windows capture longer-term trends
            but introduce more NaN rows at series boundaries.

    Returns:
        DataFrame with original columns plus rolling stat columns.
        Column count increases by ``len(sensor_cols) * len(window_sizes) * 5``.

    Raises:
        ValueError: If no sensor columns are found or specified.
    """
    if window_sizes is None:
        window_sizes = [5, 10, 20]
    if sensor_cols is None:
        sensor_cols = sorted(
            [c for c in df.columns if c.startswith("s") and c[1:].isdigit()]
        )

    if not sensor_cols:
        raise ValueError("No sensor columns found. Pass sensor_cols explicitly.")

    result = df.copy()

    for window in window_sizes:
        for col in sensor_cols:
            grouped = result.groupby("unit_id")[col]

            result[f"{col}_rolling_mean_{window}"] = grouped.transform(
                lambda x, w=window: x.rolling(window=w, min_periods=1).mean()
            )
            result[f"{col}_rolling_std_{window}"] = grouped.transform(
                lambda x, w=window: x.rolling(window=w, min_periods=1).std().fillna(0)
            )
            result[f"{col}_rolling_min_{window}"] = grouped.transform(
                lambda x, w=window: x.rolling(window=w, min_periods=1).min()
            )
            result[f"{col}_rolling_max_{window}"] = grouped.transform(
                lambda x, w=window: x.rolling(window=w, min_periods=1).max()
            )
            result[f"{col}_rolling_range_{window}"] = (
                result[f"{col}_rolling_max_{window}"]
                - result[f"{col}_rolling_min_{window}"]
            )

    new_col_count = len(result.columns) - len(df.columns)
    logger.info(
        "Rolling stats: {n} new features ({sensors} sensors × {windows} windows × 5 stats)",
        n=new_col_count,
        sensors=len(sensor_cols),
        windows=len(window_sizes),
    )
    return result


def compute_rul_labels(
    df: pd.DataFrame,
    max_rul_cap: int = 125,
    unit_col: str = "unit_id",
    cycle_col: str = "cycle",
) -> pd.DataFrame:
    """Compute Remaining Useful Life labels with piece-wise linear capping.

    For each unit, RUL is calculated as ``max_cycle - current_cycle``.
    Values above ``max_rul_cap`` are clipped to the cap, creating a
    piece-wise linear target: flat at the cap during early life, then
    linearly decreasing toward failure.

    This capping strategy prevents the model from wasting capacity
    distinguishing between "very healthy" states (e.g. RUL=200 vs
    RUL=300) that are operationally identical.

    Args:
        df: DataFrame with unit identifier and cycle columns.
        max_rul_cap: Upper bound for RUL values. Industry standard
            for C-MAPSS is 125 cycles.
        unit_col: Column name for the equipment unit identifier.
        cycle_col: Column name for the cycle number.

    Returns:
        DataFrame with an added ``rul`` column (int-typed).

    Raises:
        KeyError: If unit_col or cycle_col is missing from the DataFrame.
    """
    for col in (unit_col, cycle_col):
        if col not in df.columns:
            raise KeyError(f"Required column '{col}' not found in DataFrame")

    result = df.copy()
    max_cycles = result.groupby(unit_col)[cycle_col].transform("max")
    result["rul"] = (max_cycles - result[cycle_col]).clip(upper=max_rul_cap).astype(int)

    logger.info(
        "RUL labels: range [{lo}, {hi}], cap={cap}, {units} units",
        lo=result["rul"].min(),
        hi=result["rul"].max(),
        cap=max_rul_cap,
        units=result[unit_col].nunique(),
    )
    return result


def create_lag_features(
    df: pd.DataFrame,
    sensor_cols: list[str] | None = None,
    lags: list[int] | None = None,
) -> pd.DataFrame:
    """Create lagged sensor features within each unit's time series.

    For each sensor and lag value, adds a column ``{sensor}_lag_{n}``
    containing the sensor value from ``n`` cycles ago. Lag features
    capture temporal dynamics — how quickly a sensor is changing.

    All lags are computed per-unit to prevent cross-unit contamination
    (unit boundaries produce NaN, not values from a different unit).

    Args:
        df: DataFrame with sensor readings. Must contain a ``unit_id``
            column and be sorted by ``unit_id`` and ``cycle``.
        sensor_cols: Sensor columns to create lags for. Defaults to
            all columns matching the pattern ``s\\d+``.
        lags: Lag periods in cycles. Defaults to ``[1, 5, 10]``.
            Lag-1 captures immediate change; lag-10 captures weekly
            patterns in daily-reading scenarios.

    Returns:
        DataFrame with original columns plus lag feature columns.

    Raises:
        ValueError: If no sensor columns are found or specified.
    """
    if lags is None:
        lags = [1, 5, 10]
    if sensor_cols is None:
        sensor_cols = sorted(
            [c for c in df.columns if c.startswith("s") and c[1:].isdigit()]
        )

    if not sensor_cols:
        raise ValueError("No sensor columns found. Pass sensor_cols explicitly.")

    result = df.copy()

    for lag in lags:
        for col in sensor_cols:
            result[f"{col}_lag_{lag}"] = result.groupby("unit_id")[col].shift(lag)

    new_col_count = len(result.columns) - len(df.columns)
    logger.info(
        "Lag features: {n} new columns ({sensors} sensors × {lags} lags)",
        n=new_col_count,
        sensors=len(sensor_cols),
        lags=len(lags),
    )
    return result


def create_rate_of_change_features(
    df: pd.DataFrame,
    sensor_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Compute cycle-over-cycle rate of change for sensor readings.

    Adds a ``{sensor}_roc`` column for each sensor, containing the
    first difference (current - previous cycle) within each unit.

    Args:
        df: DataFrame with sensor readings, sorted by unit_id and cycle.
        sensor_cols: Sensor columns to differentiate. Defaults to
            all columns matching the pattern ``s\\d+``.

    Returns:
        DataFrame with added rate-of-change columns.

    Raises:
        ValueError: If no sensor columns are found or specified.
    """
    if sensor_cols is None:
        sensor_cols = sorted(
            [c for c in df.columns if c.startswith("s") and c[1:].isdigit()]
        )

    if not sensor_cols:
        raise ValueError("No sensor columns found. Pass sensor_cols explicitly.")

    result = df.copy()

    for col in sensor_cols:
        result[f"{col}_roc"] = result.groupby("unit_id")[col].diff()

    logger.info(
        "Rate-of-change: {n} new columns",
        n=len(sensor_cols),
    )
    return result


def build_feature_set(
    df: pd.DataFrame,
    sensor_cols: list[str] | None = None,
    window_sizes: list[int] | None = None,
    lags: list[int] | None = None,
    max_rul_cap: int = 125,
    drop_na: bool = True,
) -> pd.DataFrame:
    """Build the complete ML-ready feature set in one call.

    Applies all feature transforms in the correct order: sort → rolling
    stats → lag features → rate of change → RUL labels → drop NaN.

    Args:
        df: Raw sensor DataFrame with ``unit_id`` and ``cycle`` columns.
        sensor_cols: Sensor columns for feature computation.
        window_sizes: Rolling window sizes for ``rolling_sensor_stats``.
        lags: Lag periods for ``create_lag_features``.
        max_rul_cap: RUL cap value for ``compute_rul_labels``.
        drop_na: Whether to drop rows with NaN values introduced by
            rolling/lag operations. Defaults to True.

    Returns:
        ML-ready DataFrame with all engineered features and RUL labels.
    """
    logger.info("Building feature set from {n} records", n=len(df))

    result = df.sort_values(["unit_id", "cycle"]).reset_index(drop=True)
    result = rolling_sensor_stats(result, sensor_cols, window_sizes)
    result = create_lag_features(result, sensor_cols, lags)
    result = create_rate_of_change_features(result, sensor_cols)
    result = compute_rul_labels(result, max_rul_cap)

    rows_before = len(result)
    if drop_na:
        result = result.dropna().reset_index(drop=True)

    logger.info(
        "Feature set complete: {rows} records, {cols} columns "
        "({dropped} rows dropped as NaN)",
        rows=len(result),
        cols=len(result.columns),
        dropped=rows_before - len(result),
    )
    return result
