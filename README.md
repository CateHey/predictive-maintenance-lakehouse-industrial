# Predictive Maintenance Lakehouse — Industrial IoT

> End-to-end data engineering pipeline for predictive maintenance of rotating equipment in mining and heavy industry, built on a **Medallion Architecture** (Bronze → Silver → Gold) with Delta Lake, XGBoost RUL prediction, and MLflow experiment tracking.

---

## Problem Statement

Mining and industrial operations depend on high-availability rotating equipment — haul truck engines, conveyor drives, SAG mill motors, and ventilation turbines. Unplanned failures trigger cascade shutdowns, safety incidents, and production losses.

**The cost of unplanned downtime in Australian mining:**
- Open-pit haul truck: **$50K–$150K per hour** (lost haulage + cascade delays)
- SAG mill shutdown: **$200K–$500K per hour** (entire processing plant idles)
- Underground ventilation failure: **site evacuation** (safety-critical, production halt)

This project demonstrates a production-grade data engineering pipeline that transforms raw sensor telemetry into actionable maintenance predictions, reducing unplanned downtime by enabling **condition-based maintenance scheduling**.

---

## Business Impact

| Metric | Reactive Maintenance | Predictive Maintenance | Improvement |
|--------|---------------------|----------------------|-------------|
| Unplanned downtime | 15–20% of operating hours | 3–5% of operating hours | **75% reduction** |
| Maintenance cost | $0.24/unit/operating hour | $0.18/unit/operating hour | **25% savings** |
| Equipment lifespan | Baseline | +20–40% extension | **30% avg** |
| Safety incidents (mechanical) | 12/year per site | 3/year per site | **75% reduction** |
| Mean time to repair (MTTR) | 8–12 hours | 2–4 hours (planned) | **70% faster** |

**Projected value at scale:** A mid-tier Australian mining operation running 50 haul trucks at $80K/hr downtime cost, reducing unplanned stops from 200 hrs/year to 50 hrs/year = **$12M annual savings** per site.

*Sources: McKinsey Mining & Metals (2023), Deloitte Predictive Maintenance Study (2022), Australian Mining Industry Council benchmarks.*

---

## Architecture

<p align="center">
  <img src="docs/architecture.png" alt="Pipeline Architecture" width="800">
</p>

> *If the image above doesn't render, see the text diagram below.*

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  NASA FD001  │────▶│  Streaming Sim   │────▶│   Bronze Delta   │────▶│   Silver Delta   │
│  (raw .txt)  │     │  (JSON batches)  │     │  (raw telemetry) │     │  (validated +    │
└─────────────┘     └──────────────────┘     └──────────────────┘     │   drift-checked) │
                                                                       └────────┬─────────┘
                                                                                │
                    ┌──────────────────┐     ┌──────────────────┐               │
                    │    Streamlit     │◀────│   Gold Delta     │◀──────────────┘
                    │   Dashboard      │     │  (ML-ready +     │
                    └──────────────────┘     │   RUL labels)    │
                                             └────────┬─────────┘
                                                      │
                                             ┌────────▼─────────┐
                                             │  XGBoost + MLflow │
                                             │  (RUL prediction) │
                                             └──────────────────┘
```

### Medallion Layers

| Layer | Table | Purpose | Key Guarantees |
|-------|-------|---------|---------------|
| **Bronze** | `bronze_sensor_readings` | Raw ingestion with schema enforcement | Idempotent MERGE, full lineage |
| **Silver** | `silver_sensor_readings_validated` | Data quality checks + drift detection | Quality metrics logged, flagged records filtered |
| **Gold** | `gold_features_rul` | Feature engineering + RUL labels | Z-ORDERed on unit_id, ML-ready |

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Compute | Databricks Free Edition | Notebook execution, Spark clusters |
| Storage | Delta Lake | ACID transactions, schema evolution, time travel |
| Governance | Unity Catalog | Namespace structure, access control signaling |
| Ingestion | Auto Loader (cloudFiles) | Incremental file processing with checkpointing |
| Streaming Sim | Python + loguru | Local telemetry simulation from FD001 data |
| Data Quality | Custom Python (rolling z-score) | Sensor drift detection, frequency compliance |
| Feature Eng. | Pandas + PySpark | Rolling stats, lag features, RUL labels |
| ML Training | XGBoost 2.0 | Gradient-boosted RUL regression |
| Experiment Tracking | MLflow 2.9 | Parameters, metrics, model registry |
| Dashboard | Streamlit + Plotly | Fleet monitoring, alerts, drill-down |
| Testing | pytest | Unit tests for quality + feature modules |
| Linting | Ruff | Fast Python linting and formatting |
| Language | Python 3.11 | All pipeline and application code |

---

## Dataset

### NASA C-MAPSS Turbofan Engine Degradation Simulation — FD001

| Property | Value |
|----------|-------|
| Engine units | 100 (run to failure) |
| Sensor channels | 21 per reading |
| Operational settings | 3 per reading |
| Operating conditions | 1 (single regime) |
| Fault modes | 1 (HPC degradation) |
| Total cycles | ~20,631 across all units |

| File | Description |
|------|-------------|
| `train_FD001.txt` | Full degradation trajectories (100 units) |
| `test_FD001.txt` | Right-censored trajectories (100 units) |
| `RUL_FD001.txt` | True remaining life for test set |

### Why C-MAPSS as a Mining Equipment Proxy

The sensor profiles and degradation patterns in C-MAPSS turbofan data are directly analogous to mining rotating equipment:

| Turbofan Sensor | Mining Equipment Equivalent |
|----------------|---------------------------|
| Total temperature (T2, T24, T30, T50) | Thermocouple arrays on engine blocks, mill bearings |
| Total pressure (P2, P15, P30) | Hydraulic pressure transducers on haul truck systems |
| Physical fan/core speed (Nf, Nc) | Tachometer readings on conveyor drives, mill motors |
| Bypass ratio, bleed enthalpy | Vibration accelerometers, oil analysis sensors |

The key insight: **degradation is degradation** — whether a turbofan's HPC efficiency drops or a haul truck engine's compression ratio declines, the statistical signature in rolling sensor statistics follows the same patterns.

---

## Pipeline Walkthrough

### 1. Streaming Simulator
**`src/streaming_simulator.py`** — Reads raw NASA files and emits timestamped JSON batches to `data/streaming/`, simulating a real-time telemetry feed. Configurable batch size, delay, and max batches via CLI. Graceful Ctrl+C shutdown.

### 2. Bronze Ingestion
**`notebooks/01_bronze_ingestion.py`** — Uses Auto Loader (cloudFiles) with schema enforcement to ingest JSON batches. MERGE on `(unit_id, cycle)` for idempotent re-processing. Adds `_ingestion_timestamp`, `_source_file`, `_pipeline_version` metadata. Partitioned by `_ingestion_date`.

### 3. Silver Transformations
**`notebooks/02_silver_transformations.py`** — Imports `src.data_quality` module to apply:
- **Sensor drift detection:** Rolling z-score (window=20, threshold=3.0) per unit
- **Reading frequency compliance:** Missing cycle and duplicate detection
- **Operational mode validation:** Settings within expected envelope

Quality metrics are logged to a separate `quality_metrics` Delta table. Only records passing all checks are promoted to Silver.

### 4. Gold Feature Engineering
**`notebooks/03_gold_feature_engineering.py`** — Imports `src.feature_engineering` to compute:
- Rolling statistics (mean, std, min, max, range) across windows [5, 10, 20]
- Lag features at [1, 5, 10] cycles
- Rate-of-change (first difference)
- RUL labels with piece-wise linear capping at 125

Z-ORDER optimization on `unit_id` for ML training query performance.

### 5. Model Training
**`notebooks/04_model_training_mlflow.py`** — XGBoost regressor with unit-aware 80/20 split. MLflow autolog captures all parameters and metrics. Per-bucket accuracy (CRITICAL/WARNING/HEALTHY) provides operationally meaningful evaluation. Model registered as `rul_predictor` in Staging.

### 6. Dashboard
**`dashboard/app.py`** — Three-tab Streamlit interface with sidebar filters, KPI cards, sensor drill-down, RUL gauge, color-coded alert table, and CSV export.

---

## Model & MLflow

### Why XGBoost?

1. **Tabular data champion** — consistently top-performing on structured sensor data
2. **Feature importance** — built-in importance scores identify which sensors matter most
3. **Fast training** — trains in seconds on FD001, scales to millions of rows
4. **Robust to noise** — handles sensor noise and missing values gracefully
5. **Industry standard** — widely deployed in mining condition-monitoring systems

### Key Metrics

| Metric | Description | Typical Range (FD001) |
|--------|-------------|----------------------|
| RMSE | Root mean squared error | 15–25 cycles |
| MAE | Mean absolute error | 12–18 cycles |
| R² | Coefficient of determination | 0.75–0.90 |
| Bucket Accuracy | Correct CRITICAL/WARNING/HEALTHY classification | 0.80–0.92 |

### MLflow Tracking

All experiments are tracked in MLflow with:
- Hyperparameters (n_estimators, max_depth, learning_rate, etc.)
- Dataset metadata (split strategy, train/val unit counts)
- Regression metrics (RMSE, MAE, R²)
- Per-bucket accuracy (CRITICAL 0–50, WARNING 50–100, HEALTHY 100+)
- Feature importance rankings
- Registered model with stage transition

<!-- TODO: Add MLflow UI screenshots -->

---

## Dashboard

### Tab 1: Fleet Overview
KPI cards (total units, at-risk, avg RUL, critical alerts), RUL distribution histogram with risk-level coloring, and top-10 at-risk units table.

### Tab 2: Unit Health Deep Dive
Unit selector, RUL gauge indicator, degradation trajectory plot with threshold lines, and multi-sensor time series overlay.

### Tab 3: Predictions & Alerts
Severity breakdown cards, full predictions table with color-coded rows (red/yellow/green), CSV export button, and sortable columns.

<!-- TODO: Add dashboard screenshots -->

---

## Setup Instructions (Windows)

### Prerequisites
- Python 3.11+
- Git
- Databricks Community Edition account ([sign up free](https://community.cloud.databricks.com))
- Kaggle account (for dataset download)

### Step 1: Clone & Environment

```powershell
git clone https://github.com/<your-username>/predictive-maintenance-lakehouse-industrial.git
cd predictive-maintenance-lakehouse-industrial

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2: Kaggle API Token

```powershell
# Set your Kaggle token (get it from kaggle.com → Settings → API → Create New Token)
[System.Environment]::SetEnvironmentVariable('KAGGLE_API_TOKEN', '{"username":"your_user","key":"your_key"}', 'User')

# Restart your terminal, then download the dataset
python src/download_dataset.py
```

### Step 3: Run Streaming Simulator

```powershell
python src/streaming_simulator.py --batch-size 10 --delay-seconds 1 --max-batches 100
```

### Step 4: Run Tests

```powershell
pytest tests/ -v
```

### Step 5: Databricks Setup

1. Upload `notebooks/` to your Databricks workspace (Import → File)
2. Upload `src/` via Repos or as workspace files
3. Upload `data/streaming/` JSON files to `/Volumes/main/default/streaming/` (or `/FileStore/streaming/` on Community)
4. Run notebooks in order: `01` → `02` → `03` → `04`
5. Export Gold table as parquet for local dashboard: `gold_df.toPandas().to_parquet("gold_features.parquet")`

### Step 6: Launch Dashboard

```powershell
# Place exported parquet in data/gold/ (or use raw fallback)
streamlit run dashboard/app.py
```

---

## Future Enhancements

- [ ] **Unity Catalog full governance** — row-level security, column masking for sensitive sensor data
- [ ] **Azure Event Hubs / Kafka** — replace streaming simulator with production message bus
- [ ] **Model drift monitoring** — track prediction accuracy degradation over time with Evidently AI
- [ ] **A/B testing framework** — compare XGBoost vs. LSTM vs. Transformer architectures
- [ ] **Edge deployment** — ONNX model export for on-truck telematics units (Caterpillar MineStar, Komatsu FrontRunner)
- [ ] **Multi-fault mode** — extend to FD002–FD004 datasets for multi-regime, multi-failure scenarios
- [ ] **Great Expectations** — declarative data quality contracts replacing custom checks
- [ ] **Databricks Workflows** — orchestrated pipeline with dependency management and alerting
- [ ] **Cost optimization module** — balance maintenance cost vs. downtime cost for optimal scheduling
- [ ] **Terraform IaC** — Databricks workspace provisioning for multi-site mining deployments

---

## License

MIT

---

*Built as a portfolio project demonstrating senior-level data engineering practices for industrial predictive maintenance in the Australian mining sector.*
