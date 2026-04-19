"""Streamlit dashboard for Predictive Maintenance fleet monitoring.

Three-tab interface for mining operations equipment health:
1. Fleet Overview — KPI cards, RUL histogram, top at-risk units
2. Unit Health Deep Dive — sensor time series, RUL gauge, degradation trajectory
3. Predictions & Alerts — color-coded table, CSV export, severity breakdown

Reads from local parquet files exported from Databricks Gold Delta table.
Falls back to raw FD001 data with on-the-fly feature engineering for demos.
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
GOLD_PATH = DATA_DIR / "gold"
RAW_PATH = DATA_DIR / "raw" / "train_FD001.txt"

CMAPSS_COLUMNS: list[str] = [
    "unit_id", "cycle",
    "op_setting_1", "op_setting_2", "op_setting_3",
    *(f"s{i}" for i in range(1, 22)),
]

RISK_COLORS: dict[str, str] = {
    "CRITICAL": "#EF4444",
    "WARNING": "#F59E0B",
    "HEALTHY": "#10B981",
}

CUSTOM_CSS = """
<style>
    /* KPI card styling */
    div[data-testid="stMetric"] {
        background-color: #1E293B;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 16px 20px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
    }
    div[data-testid="stMetric"] label {
        color: #94A3B8;
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #F1F5F9;
        font-size: 1.8rem;
        font-weight: 700;
    }
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 20px;
        border-radius: 6px 6px 0 0;
    }
    /* Table header */
    thead tr th {
        background-color: #1E293B !important;
        color: #E2E8F0 !important;
        font-weight: 600;
    }
    /* Sidebar title */
    section[data-testid="stSidebar"] h1 {
        font-size: 1.2rem;
        color: #F59E0B;
    }
</style>
"""


@st.cache_data
def load_data() -> pd.DataFrame:
    """Load sensor data from Gold parquet or raw FD001 with fallback features.

    Returns:
        DataFrame with sensor readings, engineered features, and RUL labels.
    """
    parquet_files = list(GOLD_PATH.glob("*.parquet")) if GOLD_PATH.exists() else []

    if parquet_files:
        df = pd.read_parquet(GOLD_PATH)
        logger.info(f"Loaded Gold parquet: {len(df)} records from {GOLD_PATH}")
        return df

    logger.info("Gold parquet not found — falling back to raw FD001 data")

    if not RAW_PATH.exists():
        st.error(
            f"No data found. Place `train_FD001.txt` in `{DATA_DIR / 'raw'}` "
            f"or export Gold Delta as parquet to `{GOLD_PATH}`."
        )
        st.stop()

    df = pd.read_csv(RAW_PATH, sep=r"\s+", header=None, names=CMAPSS_COLUMNS)

    max_cycles = df.groupby("unit_id")["cycle"].transform("max")
    df["rul"] = (max_cycles - df["cycle"]).clip(upper=125).astype(int)

    sensor_cols = [f"s{i}" for i in range(1, 22)]
    for sensor in sensor_cols:
        df[f"{sensor}_rolling_mean_5"] = (
            df.groupby("unit_id")[sensor]
            .transform(lambda x: x.rolling(5, min_periods=1).mean())
        )

    logger.info(f"Loaded raw FD001: {len(df)} records, {df['unit_id'].nunique()} units")
    return df


def get_latest_predictions(df: pd.DataFrame) -> pd.DataFrame:
    """Get the last reading per unit with RUL and risk classification.

    Args:
        df: Full sensor DataFrame with RUL column.

    Returns:
        One row per unit with risk_level categorization.
    """
    latest = df.sort_values("cycle").groupby("unit_id").last().reset_index()
    latest["risk_level"] = pd.cut(
        latest["rul"],
        bins=[-1, 50, 100, float("inf")],
        labels=["CRITICAL", "WARNING", "HEALTHY"],
    )
    return latest


def apply_sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Render sidebar filters and return filtered DataFrame.

    Args:
        df: Full sensor DataFrame.

    Returns:
        Filtered DataFrame based on user selections.
    """
    st.sidebar.title("Filters")

    cycle_min, cycle_max = int(df["cycle"].min()), int(df["cycle"].max())
    cycle_range = st.sidebar.slider(
        "Cycle Range",
        min_value=cycle_min,
        max_value=cycle_max,
        value=(cycle_min, cycle_max),
    )

    if "op_setting_3" in df.columns:
        op_modes = sorted(df["op_setting_3"].round(0).unique())
        selected_modes = st.sidebar.multiselect(
            "Operational Mode (op_setting_3)",
            options=op_modes,
            default=op_modes,
        )
        if selected_modes:
            df = df[df["op_setting_3"].round(0).isin(selected_modes)]

    filtered = df[(df["cycle"] >= cycle_range[0]) & (df["cycle"] <= cycle_range[1])]

    st.sidebar.markdown("---")
    st.sidebar.metric("Filtered Records", f"{len(filtered):,}")
    st.sidebar.metric("Active Units", filtered["unit_id"].nunique())

    return filtered


def render_fleet_overview(df: pd.DataFrame, latest: pd.DataFrame) -> None:
    """Render Tab 1: Fleet Overview with KPIs, histogram, and at-risk table.

    Args:
        df: Full filtered sensor DataFrame.
        latest: One row per unit with risk levels.
    """
    total_units = latest["unit_id"].nunique()
    at_risk = int((latest["rul"] < 50).sum())
    avg_rul = latest["rul"].mean()
    critical_alerts = int((latest["rul"] < 25).sum())

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Units", total_units)
    col2.metric("Units At Risk", at_risk, delta=f"{at_risk}" if at_risk > 0 else None, delta_color="inverse")
    col3.metric("Avg RUL", f"{avg_rul:.0f} cycles")
    col4.metric("Critical Alerts", critical_alerts, delta=f"{critical_alerts}" if critical_alerts > 0 else None, delta_color="inverse")

    st.markdown("---")

    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.subheader("RUL Distribution")
        fig_hist = px.histogram(
            latest, x="rul", nbins=25,
            color="risk_level",
            color_discrete_map=RISK_COLORS,
            category_orders={"risk_level": ["CRITICAL", "WARNING", "HEALTHY"]},
            labels={"rul": "Remaining Useful Life (cycles)", "count": "Units"},
        )
        fig_hist.update_layout(
            bargap=0.05,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#E2E8F0",
            legend_title_text="Risk Level",
        )
        fig_hist.add_vline(x=50, line_dash="dash", line_color="#EF4444", annotation_text="Critical")
        fig_hist.add_vline(x=100, line_dash="dash", line_color="#F59E0B", annotation_text="Warning")
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_right:
        st.subheader("Risk Breakdown")
        risk_counts = latest["risk_level"].value_counts().reindex(["CRITICAL", "WARNING", "HEALTHY"], fill_value=0)
        fig_pie = px.pie(
            values=risk_counts.values,
            names=risk_counts.index,
            color=risk_counts.index,
            color_discrete_map=RISK_COLORS,
            hole=0.4,
        )
        fig_pie.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#E2E8F0",
            showlegend=True,
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    st.subheader("Top 10 At-Risk Units")
    at_risk_df = (
        latest[["unit_id", "cycle", "rul", "risk_level"]]
        .sort_values("rul")
        .head(10)
        .rename(columns={
            "unit_id": "Unit ID",
            "cycle": "Last Cycle",
            "rul": "Predicted RUL",
            "risk_level": "Risk Level",
        })
    )
    st.dataframe(at_risk_df, use_container_width=True, hide_index=True)


def render_unit_deep_dive(df: pd.DataFrame) -> None:
    """Render Tab 2: Unit Health Deep Dive with sensors, gauge, and trajectory.

    Args:
        df: Full filtered sensor DataFrame.
    """
    units = sorted(df["unit_id"].unique())
    selected_unit = st.selectbox("Select Unit", units, index=0)
    unit_df = df[df["unit_id"] == selected_unit].sort_values("cycle")

    current_rul = int(unit_df["rul"].iloc[-1]) if "rul" in unit_df.columns else 0
    max_cycle = int(unit_df["cycle"].max())
    total_cycles = len(unit_df)

    col1, col2, col3 = st.columns(3)
    col1.metric("Current RUL", f"{current_rul} cycles")
    col2.metric("Max Cycle", max_cycle)
    col3.metric("Total Readings", total_cycles)

    gauge_col, trajectory_col = st.columns(2)

    with gauge_col:
        st.subheader("RUL Gauge")
        gauge_color = "#EF4444" if current_rul < 50 else "#F59E0B" if current_rul < 100 else "#10B981"
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=current_rul,
            title={"text": f"Unit {selected_unit} — Remaining Useful Life"},
            gauge={
                "axis": {"range": [0, 125]},
                "bar": {"color": gauge_color},
                "steps": [
                    {"range": [0, 50], "color": "rgba(239,68,68,0.2)"},
                    {"range": [50, 100], "color": "rgba(245,158,11,0.2)"},
                    {"range": [100, 125], "color": "rgba(16,185,129,0.2)"},
                ],
                "threshold": {
                    "line": {"color": "#EF4444", "width": 3},
                    "thickness": 0.8,
                    "value": 50,
                },
            },
        ))
        fig_gauge.update_layout(
            height=300,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#E2E8F0",
        )
        st.plotly_chart(fig_gauge, use_container_width=True)

    with trajectory_col:
        st.subheader("Degradation Trajectory")
        if "rul" in unit_df.columns:
            fig_rul = px.line(
                unit_df, x="cycle", y="rul",
                labels={"cycle": "Operating Cycle", "rul": "RUL (cycles)"},
            )
            fig_rul.add_hline(y=50, line_dash="dash", line_color="#EF4444", annotation_text="Critical")
            fig_rul.add_hline(y=100, line_dash="dash", line_color="#F59E0B", annotation_text="Warning")
            fig_rul.update_layout(
                height=300,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#E2E8F0",
            )
            st.plotly_chart(fig_rul, use_container_width=True)

    st.markdown("---")
    st.subheader("Sensor Time Series")

    raw_sensor_cols = sorted([
        c for c in unit_df.columns
        if c.startswith("s") and c[1:].isdigit()
    ])

    selected_sensors = st.multiselect(
        "Select sensors to plot",
        raw_sensor_cols,
        default=raw_sensor_cols[:3] if len(raw_sensor_cols) >= 3 else raw_sensor_cols,
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
            height=400,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#E2E8F0",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_sensors, use_container_width=True)


def render_predictions_alerts(latest: pd.DataFrame) -> None:
    """Render Tab 3: Predictions table, CSV export, and severity breakdown.

    Args:
        latest: One row per unit with risk_level classification.
    """
    severity_col, export_col = st.columns([2, 1])

    with severity_col:
        st.subheader("Alert Count by Severity")
        severity_counts = latest["risk_level"].value_counts().reindex(
            ["CRITICAL", "WARNING", "HEALTHY"], fill_value=0
        )
        sev_col1, sev_col2, sev_col3 = st.columns(3)
        sev_col1.markdown(
            f"<div style='text-align:center;padding:12px;background:#7F1D1D;border-radius:8px;'>"
            f"<span style='font-size:2rem;font-weight:700;color:#FCA5A5;'>{severity_counts.get('CRITICAL', 0)}</span>"
            f"<br><span style='color:#FCA5A5;'>CRITICAL</span></div>",
            unsafe_allow_html=True,
        )
        sev_col2.markdown(
            f"<div style='text-align:center;padding:12px;background:#78350F;border-radius:8px;'>"
            f"<span style='font-size:2rem;font-weight:700;color:#FDE68A;'>{severity_counts.get('WARNING', 0)}</span>"
            f"<br><span style='color:#FDE68A;'>WARNING</span></div>",
            unsafe_allow_html=True,
        )
        sev_col3.markdown(
            f"<div style='text-align:center;padding:12px;background:#064E3B;border-radius:8px;'>"
            f"<span style='font-size:2rem;font-weight:700;color:#6EE7B7;'>{severity_counts.get('HEALTHY', 0)}</span>"
            f"<br><span style='color:#6EE7B7;'>HEALTHY</span></div>",
            unsafe_allow_html=True,
        )

    with export_col:
        st.subheader("Export")
        export_df = latest[["unit_id", "cycle", "rul", "risk_level"]].sort_values("rul")
        csv_data = export_df.to_csv(index=False)
        st.download_button(
            label="Download Predictions (CSV)",
            data=csv_data,
            file_name="rul_predictions.csv",
            mime="text/csv",
        )

    st.markdown("---")
    st.subheader("All Predictions")

    st.markdown("""
    | Color | RUL Range | Action Required |
    |-------|-----------|-----------------|
    | Red | < 50 cycles | Immediate maintenance — pull from service |
    | Yellow | 50–100 cycles | Schedule maintenance window this rotation |
    | Green | > 100 cycles | Normal operations — continue monitoring |
    """)

    display_df = (
        latest[["unit_id", "cycle", "rul", "risk_level"]]
        .rename(columns={
            "unit_id": "Unit ID",
            "cycle": "Last Cycle",
            "rul": "Predicted RUL",
            "risk_level": "Risk Level",
        })
        .sort_values("Predicted RUL")
    )

    def color_rul_row(row: pd.Series) -> list[str]:
        rul = row["Predicted RUL"]
        if rul < 50:
            style = "background-color: #FEE2E2; color: #991B1B"
        elif rul < 100:
            style = "background-color: #FEF3C7; color: #92400E"
        else:
            style = "background-color: #D1FAE5; color: #065F46"
        return [style] * len(row)

    styled = display_df.style.apply(color_rul_row, axis=1)
    st.dataframe(styled, use_container_width=True, height=600, hide_index=True)


def main() -> None:
    """Dashboard entry point."""
    st.set_page_config(
        page_title="Predictive Maintenance — Mining Operations",
        page_icon="https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/2699.png",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    st.title("Predictive Maintenance Dashboard")
    st.caption("Industrial Equipment Fleet Monitoring — Mining Operations")

    df = load_data()
    df = apply_sidebar_filters(df)
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
