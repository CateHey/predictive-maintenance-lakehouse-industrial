Implement the 3 core src/ modules with senior-level code quality:

1. src/streaming_simulator.py
   - Reads data/raw/train_FD001.txt (NASA CMAPSS format: space-separated)
   - Columns: unit_id, cycle, 3 operational_settings, 21 sensors (s1-s21)
   - Simulates streaming by writing JSON batches to data/streaming/
   - Configurable: batch_size, delay_seconds, max_batches via argparse
   - Each batch = list of sensor readings with timestamp
   - Graceful shutdown on Ctrl+C
   - Loguru structured logs: "Batch N written, X records, next in Ys"

2. src/data_quality.py
   - sensor_drift_detection(df, sensor_cols, window=20, z_threshold=3.0) 
     returns DataFrame with drift_flag column using rolling z-score
   - reading_frequency_compliance(df, expected_interval_sec=1.0) 
     returns quality_score 0-1
   - operational_mode_validation(df, op_setting_cols) 
     flags records outside expected operational envelope
   - All functions return (cleaned_df, quality_report: dict)
   - Quality report includes: total_records, records_flagged, 
     flag_rate, per_sensor_drift_count

3. src/feature_engineering.py
   - rolling_sensor_stats(df, sensor_cols, window_sizes=[5,10,20]) 
     adds mean, std, min, max, range per window
   - compute_rul_labels(df, max_rul_cap=125) 
     adds RUL column per unit (piece-wise linear capping)
   - create_lag_features(df, sensor_cols, lags=[1,5,10])

All modules:
- Type hints (use typing module)
- Google-style docstrings with Args, Returns, Raises
- Loguru for logging
- Pandas + PySpark-compatible where possible (dual implementation 
  with @overload if needed, OR clear docstring stating "Pandas only")
- No bare except clauses

Conversación 3 — Databricks notebooks (los 4)
Prompt para Claude Code:
Generate 4 Databricks notebooks using Databricks format 
(# Databricks notebook source + # COMMAND ---------- separators):

NOTEBOOK 1: notebooks/01_bronze_ingestion.py
- Reads JSON streaming files from /Volumes/main/default/streaming/ 
  (or /FileStore/streaming/ for Community)
- Uses Auto Loader (cloudFiles) with schema inference + schema evolution
- Writes Delta table "bronze_sensor_readings" with:
  - Schema enforcement
  - Partitioning by ingestion_date
  - Checkpointing
  - MERGE for idempotency on (unit_id, cycle)
- Adds metadata columns: _ingestion_timestamp, _source_file
- Cell structure: Config → Read → Transform → Write → Validate

NOTEBOOK 2: notebooks/02_silver_transformations.py
- Reads bronze Delta
- Imports from src.data_quality (document how to configure in 
  Databricks: %pip install or workspace files)
- Applies drift detection, frequency compliance, op mode validation
- Logs quality metrics to Delta table "quality_metrics" 
  (for observability dashboard)
- Writes Silver Delta "silver_sensor_readings_validated" 
  (only records passing QC)
- Uses Delta time travel friendly writes (mode=overwrite with schema merge)

NOTEBOOK 3: notebooks/03_gold_feature_engineering.py
- Reads Silver
- Applies rolling_sensor_stats, create_lag_features from 
  src.feature_engineering
- Computes compute_rul_labels per unit
- Writes Gold Delta "gold_features_rul" with clear column lineage
- Includes Z-ORDER optimization on unit_id for ML training queries

NOTEBOOK 4: notebooks/04_model_training_mlflow.py
- Reads Gold Delta
- Train/validation split BY UNIT (not random) — 80/20 units
- Why by unit: prevent data leakage across time within same engine
- XGBoost regressor for RUL prediction
- MLflow autolog enabled
- Logs hyperparameters, metrics: RMSE, MAE, R², per-bucket accuracy 
  (RUL 0-50, 50-100, 100+)
- Registers model to MLflow Model Registry as "rul_predictor" 
  with stage "Staging"
- Final cell: load model from registry, predict on test set, 
  show example predictions

All notebooks:
- First cell: title + description in markdown (# %md)
- Parameterize paths with dbutils.widgets
- Error handling with clear messages
- Print summary statistics at end (row counts, schema, sample)

Conversación 4 — Streamlit dashboard + tests + README + docs
Prompt para Claude Code:
Generate the remaining files:

1. dashboard/app.py (Streamlit)
   - Reads from local parquet files in data/gold/ (export from 
     Databricks as parquet for local dashboard demo)
   - Uses @st.cache_data for data loading
   - Sidebar: global filters (date range, operational mode)
   - Tab 1 "Fleet Overview":
     - KPI cards: Total Units, Units At Risk (RUL<50), Avg RUL, 
       Critical Alerts
     - Bar chart: RUL distribution histogram
     - Small table: Top 10 at-risk units
   - Tab 2 "Unit Health Deep Dive":
     - Selectbox: choose unit_id
     - Line charts: sensor readings over time (multi-sensor selector)
     - Gauge: current RUL estimate
     - Degradation trajectory plot
   - Tab 3 "Predictions & Alerts":
     - Full predictions table sortable by RUL
     - Color-coded rows: red <50, yellow 50-100, green >100
     - Download button (CSV export)
     - Alert count by severity
   - Custom CSS for professional mining/industrial look 
     (dark theme optional, clean layout)

2. tests/test_feature_engineering.py (pytest)
   - test_rolling_sensor_stats_adds_correct_columns
   - test_compute_rul_labels_caps_at_max
   - test_create_lag_features_handles_unit_boundaries 
     (no leakage across units)

3. tests/test_data_quality.py (pytest)
   - test_sensor_drift_detection_flags_known_drift
   - test_reading_frequency_compliance_perfect_score

4. README.md (replace existing)
   Structure:
   # Predictive Maintenance Lakehouse — Industrial IoT
   
   ## Problem Statement
   [Mining ops context, unplanned downtime costs]
   
   ## Business Impact
   [TABLE: Reactive vs Predictive with benchmarks]
   [Projected value at scale]
   
   ## Architecture
   [Reference to architecture.png + medallion description]
   
   ## Tech Stack
   [Table: Layer | Technology | Purpose]
   
   ## Dataset
   [NASA CMAPSS description, why chosen as analog for mining equipment]
   
   ## Pipeline Walkthrough
   [Bronze → Silver → Gold with notebook references]
   
   ## Model & MLflow
   [XGBoost choice rationale, metrics interpretation, 
    MLflow screenshots placeholder]
   
   ## Dashboard
   [3 tabs description, screenshots placeholder]
   
   ## Setup Instructions (Windows)
   [Step by step: clone, env vars, python venv, download dataset, 
    Databricks setup, run streaming, run notebooks, run dashboard]
   
   ## Future Enhancements
   [List: Unity Catalog full governance, real Event Hubs ingestion, 
    model drift monitoring, A/B testing framework, edge deployment 
    on truck telematics]
   
   ## License
   MIT

5. docs/medallion_architecture.md
   - Why medallion pattern (vs lambda, vs plain ETL)
   - Why Delta Lake (ACID, schema evolution, time travel)
   - Bronze layer design decisions
   - Silver layer design decisions  
   - Gold layer design decisions
   - Trade-offs considered
   - Scale considerations (current 1 engine fleet → multi-site mining ops)

Professional tone throughout. Mining/industrial framing. 
Senior engineer vocabulary.