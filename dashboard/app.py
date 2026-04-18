"""Streamlit dashboard for Predictive Maintenance fleet monitoring.

Three-tab interface:
1. Fleet Overview — KPI cards and aggregate health metrics
2. Unit Health Deep Dive — sensor time series for a selected unit
3. Predictions & Alerts — RUL predictions with color-coded risk levels
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from loguru import logger

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GOLD_PATH = DATA_DIR / "gold" / "feature_table"
RAW_PATH = DATA_DIR / "raw" / "train_FD001.txt"

SENSOR_COLUMNS: list[str] = [
    "unit_id", "cycle",
    "op_setting_1", "op_setting_2", "op_setting_3",
    *[f"sensor_{i}" for i in range(1, 22)],
]


@st.cache_data
def load_data() -> pd.DataFrame:
    """Load sensor data from raw file and compute RUL labels.

    Attempts Gold Delta table first; falls back to raw FD001 file
    with on-the-fly feature engineering for local development.
    """
    try:
        df = pd.read_parquet(GOLD_PATH)
        logger.info(f"Loaded Gold table: {len(df)} records")
        return df
    except Exception:
        logger.info("Gold table not found — loading raw data with synthetic features")

    if not RAW_PATH.exists():
        st.error(f"Data file not found: {RAW_PATH}")
        st.stop()

    df = pd.read_csv(RAW_PATH, sep=r"\s+", header=None, names=SENSOR_COLUMNS)

    max_cycles = df.groupby("unit_id")["cycle"].transform("max")
    df["rul"] = (max_cycles - df["cycle"]).clip(upper=125)

    for sensor in [f"sensor_{i}" for i in range(1, 22)]:
        df[f"{sensor}_rolling_mean_5"] = (
            df.groupby("unit_id")[sensor]
            .transform(lambda x: x.rolling(5, min_periods=1).mean())
        )

    return df


def get_latest_predictions(df: pd.DataFrame) -> pd.DataFrame:
    """Get the last reading per unit with RUL and risk classification."""
    latest = df.sort_values("cycle").groupby("unit_id").last().reset_index()
    latest["risk_level"] = pd.cut(
        latest["rul"],
        bins=[-1, 50, 100, float("inf")],
        labels=["CRITICAL", "WARNING", "HEALTHY"],
    )
    return latest


def render_fleet_overview(df: pd.DataFrame, latest: pd.DataFrame) -> None:
    """Render Tab 1: Fleet Overview with KPI cards."""
    st.header("Fleet Overview")

    total_units = latest["unit_id"].nunique()
    at_risk = int((latest["rul"] < 50).sum())
    avg_rul = latest["rul"].mean()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Units Monitored", total_units)
    col2.metric("Units At Risk (RUL < 50)", at_risk, delta=f"-{at_risk}" if at_risk > 0 else "0")
    col3.metric("Average RUL", f"{avg_rul:.0f} cycles")

    st.subheader("RUL Distribution Across Fleet")
    fig_hist = px.histogram(
        latest, x="rul", nbins=25,
        color="risk_level",
        color_discrete_map={"CRITICAL": "#EF4444", "WARNING": "#F59E0B", "HEALTHY": "#10B981"},
        title="Remaining Useful Life Distribution",
        labels={"rul": "Remaining Useful Life (cycles)", "count": "Number of Units"},
    )
    st.plotly_chart(fig_hist, use_container_width=True)

    st.subheader("Risk Level Breakdown")
    risk_counts = latest["risk_level"].value_counts().reset_index()
    risk_counts.columns = ["Risk Level", "Count"]
    fig_pie = px.pie(
        risk_counts, values="Count", names="Risk Level",
        color="Risk Level",
        color_discrete_map={"CRITICAL": "#EF4444", "WARNING": "#F59E0B", "HEALTHY": "#10B981"},
    )
    st.plotly_chart(fig_pie, use_container_width=True)


def render_unit_deep_dive(df: pd.DataFrame) -> None:
    """Render Tab 2: Unit Health Deep Dive with sensor time series."""
    st.header("Unit Health Deep Dive")

    units = sorted(df["unit_id"].unique())
    selected_unit = st.selectbox("Select Unit", units, index=0)

    unit_df = df[df["unit_id"] == selected_unit].sort_values("cycle")

    st.subheader(f"Unit {selected_unit} — RUL Trajectory")
    if "rul" in unit_df.columns:
        fig_rul = px.line(
            unit_df, x="cycle", y="rul",
            title=f"Unit {selected_unit}: Remaining Useful Life Over Time",
            labels={"cycle": "Operating Cycle", "rul": "RUL (cycles)"},
        )
        fig_rul.add_hline(y=50, line_dash="dash", line_color="red", annotation_text="Critical Threshold")
        fig_rul.add_hline(y=100, line_dash="dash", line_color="orange", annotation_text="Warning Threshold")
        st.plotly_chart(fig_rul, use_container_width=True)

    st.subheader("Sensor Time Series")
    sensor_cols = [c for c in unit_df.columns if c.startswith("sensor_") and "rolling" not in c and "lag" not in c and "roc" not in c]

    selected_sensors = st.multiselect(
        "Select sensors to plot",
        sensor_cols,
        default=["sensor_2", "sensor_3", "sensor_4"] if all(s in sensor_cols for s in ["sensor_2", "sensor_3", "sensor_4"]) else sensor_cols[:3],
    )

    if selected_sensors:
        fig_sensors = go.Figure()
        for sensor in selected_sensors:
            fig_sensors.add_trace(go.Scatter(
                x=unit_df["cycle"], y=unit_df[sensor],
                mode="lines", name=sensor,
            ))
        fig_sensors.update_layout(
            title=f"Unit {selected_unit}: Sensor Readings",
            xaxis_title="Operating Cycle",
            yaxis_title="Sensor Value",
        )
        st.plotly_chart(fig_sensors, use_container_width=True)


def render_predictions_alerts(latest: pd.DataFrame) -> None:
    """Render Tab 3: Predictions & Alerts table with color-coded RUL."""
    st.header("Predictions & Alerts")

    st.markdown("""
    | Color | RUL Range | Action |
    |-------|-----------|--------|
    | 🟢 Green | > 100 cycles | Normal operations |
    | 🟡 Yellow | 50–100 cycles | Schedule maintenance window |
    | 🔴 Red | < 50 cycles | Immediate maintenance required |
    """)

    display_df = latest[["unit_id", "cycle", "rul", "risk_level"]].copy()
    display_df.columns = ["Unit ID", "Last Cycle", "Predicted RUL", "Risk Level"]
    display_df = display_df.sort_values("Predicted RUL")

    def color_rul(val: int) -> str:
        if val < 50:
            return "background-color: #FEE2E2; color: #991B1B"
        if val < 100:
            return "background-color: #FEF3C7; color: #92400E"
        return "background-color: #D1FAE5; color: #065F46"

    styled = display_df.style.applymap(color_rul, subset=["Predicted RUL"])
    st.dataframe(styled, use_container_width=True, height=600)

    st.subheader("Critical Alerts")
    critical = display_df[display_df["Risk Level"] == "CRITICAL"]
    if not critical.empty:
        st.error(f"⚠️ {len(critical)} units require immediate maintenance attention!")
        st.dataframe(critical, use_container_width=True)
    else:
        st.success("No critical alerts — all units within safe operating limits.")


def main() -> None:
    """Main dashboard entry point."""
    st.set_page_config(
        page_title="Predictive Maintenance — Fleet Monitor",
        page_icon="⚙️",
        layout="wide",
    )

    st.title("Predictive Maintenance Dashboard")
    st.caption("Industrial Equipment Fleet Monitoring — Mining Operations")

    df = load_data()
    latest = get_latest_predictions(df)

    tab1, tab2, tab3 = st.tabs([
        "Fleet Overview",
        "Unit Health Deep Dive",
        "Predictions & Alerts",
    ])

    with tab1:
        render_fleet_overview(df, latest)

    with tab2:
        render_unit_deep_dive(df)

    with tab3:
        render_predictions_alerts(latest)


if __name__ == "__main__":
    main()
