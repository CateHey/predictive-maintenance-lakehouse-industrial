# Predictive Maintenance Lakehouse — Industrial Equipment

> End-to-end data engineering pipeline for predictive maintenance of rotating equipment, built on a Medallion Architecture (Bronze → Silver → Gold) with Delta Lake, XGBoost RUL prediction, and MLflow experiment tracking.
>
> Designed for mining and heavy-industry contexts where unplanned downtime costs **$50K–$150K per hour**.

---

## Problem Statement

Mining and industrial operations depend on high-availability rotating equipment — haul truck engines, conveyor drives, SAG mill motors, and ventilation turbines. Unplanned failures trigger cascade shutdowns, safety incidents, and production losses measured in millions per day.

This project demonstrates a production-grade data engineering pipeline that:

1. **Ingests** high-frequency sensor telemetry via a streaming simulator
2. **Cleanses and validates** data through automated quality checks and drift detection
3. **Engineers features** proven to predict Remaining Useful Life (RUL)
4. **Trains and tracks** ML models with full reproducibility via MLflow
5. **Surfaces actionable alerts** through a real-time operational dashboard

The pipeline uses NASA's C-MAPSS Turbofan Degradation dataset (FD001) as a proxy for industrial rotating equipment — the sensor profiles and degradation patterns are directly analogous to mining haul truck engines and mill drive systems.

---

## Business Impact

<!-- TODO: Write your own business impact narrative here -->

---

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  NASA FD001  │────▶│  Streaming Sim   │────▶│   Bronze Delta   │────▶│   Silver Delta   │
│  (raw .txt)  │     │  (JSON batches)  │     │  (raw telemetry) │     │  (cleansed +     │
└─────────────┘     └──────────────────┘     └──────────────────┘     │   validated)     │
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

| Layer    | Purpose                                          | Format     |
|----------|--------------------------------------------------|------------|
| **Bronze** | Raw sensor ingestion with schema enforcement     | Delta Lake |
| **Silver** | Data quality checks, drift detection, cleansing  | Delta Lake |
| **Gold**   | Feature engineering, RUL labels, ML-ready views  | Delta Lake |

---

## Tech Stack

| Component              | Technology                          |
|------------------------|-------------------------------------|
| Compute                | Databricks Free Edition (Community) |
| Storage Format         | Delta Lake                          |
| Governance             | Unity Catalog (structure signaling) |
| Streaming Simulation   | Python + loguru                     |
| ML Training            | XGBoost 2.0                         |
| Experiment Tracking    | MLflow 2.9                          |
| Dashboard              | Streamlit + Plotly                   |
| Testing                | pytest                              |
| Language               | Python 3.11                         |

---

## Dataset Description

**NASA C-MAPSS Turbofan Engine Degradation Simulation — FD001**

- **100 engine units** run to failure under a single operating condition and single fault mode
- **21 sensor channels** per reading (temperature, pressure, speed, vibration proxies)
- **3 operational settings** per reading
- **~20,631 total cycles** across all units
- Train set includes full run-to-failure; test set is right-censored

| File             | Description                                |
|------------------|--------------------------------------------|
| `train_FD001.txt`| Full degradation trajectories (100 units)  |
| `test_FD001.txt` | Right-censored trajectories (100 units)    |
| `RUL_FD001.txt`  | True remaining life for test set           |

**Mining analogy:** Each "engine unit" maps to a haul truck engine or mill drive motor. Sensor channels represent thermocouple arrays, pressure transducers, and vibration accelerometers typical in mining condition-monitoring systems.

---

## Pipeline Walkthrough

### 1. Streaming Simulator (`src/streaming_simulator.py`)
Reads raw NASA files and emits JSON batches to `data/streaming/`, simulating a real-time telemetry feed at configurable intervals.

### 2. Bronze Ingestion (`notebooks/01_bronze_ingestion.py`)
Reads JSON batches, enforces schema, and writes to Bronze Delta table with MERGE for idempotent re-processing.

### 3. Silver Transformations (`notebooks/02_silver_transformations.py`)
Applies data quality checks (drift detection, range validation, frequency compliance), logs quality metrics, and writes cleansed records to Silver.

### 4. Gold Feature Engineering (`notebooks/03_gold_feature_engineering.py`)
Computes rolling statistics, lag features, and RUL labels (capped at 125 cycles). Produces ML-ready feature table in Gold.

### 5. Model Training (`notebooks/04_model_training_mlflow.py`)
Trains XGBoost regressor with unit-aware train/validation split. Logs parameters, metrics, and model artifact to MLflow. Registers model for downstream consumption.

### 6. Dashboard (`dashboard/app.py`)
Three-tab Streamlit app: Fleet Overview, Unit Health Deep Dive, and Predictions & Alerts with color-coded RUL thresholds.

---

## Model & MLflow

- **Algorithm:** XGBoost Regressor
- **Target:** Remaining Useful Life (RUL), capped at 125 cycles
- **Split strategy:** By engine unit (no data leakage across units)
- **Metrics:** RMSE, MAE, R²
- **Tracking:** MLflow autolog with parameter, metric, and artifact capture
- **Registry:** Model registered as `rul_xgboost_fd001`

---

## Dashboard Screenshots

<!-- TODO: Add screenshots after running the dashboard -->

---

## Setup Instructions (Windows)

### Prerequisites
- Python 3.11+
- Git
- Databricks Community Edition account (free)

### Local Setup

```bash
# Clone the repository
git clone https://github.com/<your-username>/predictive-maintenance-lakehouse-industrial.git
cd predictive-maintenance-lakehouse-industrial

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Place NASA FD001 files in data/raw/
# Expected: train_FD001.txt, test_FD001.txt, RUL_FD001.txt

# Run streaming simulator
python src/streaming_simulator.py --input data/raw/train_FD001.txt --output data/streaming/ --interval 2

# Run tests
pytest tests/ -v

# Launch dashboard
streamlit run dashboard/app.py
```

### Databricks Setup

1. Upload notebooks from `notebooks/` to your Databricks workspace
2. Upload `src/` modules as workspace files or attach via Repos
3. Run notebooks in order: 01 → 02 → 03 → 04
4. Configure Unity Catalog namespace: `mining_ops.predictive_maintenance.*`

---

## Future Enhancements

- [ ] Azure Event Hubs / Kafka integration for production streaming
- [ ] Great Expectations for declarative data quality contracts
- [ ] Databricks Workflows for orchestrated pipeline scheduling
- [ ] Real-time model serving via Databricks Model Serving
- [ ] Anomaly detection ensemble (Isolation Forest + Autoencoder)
- [ ] Integration with historians (OSIsoft PI, Honeywell PHD)
- [ ] Multi-fault mode support (FD002–FD004 datasets)
- [ ] Terraform/Pulumi IaC for Databricks workspace provisioning
- [ ] Cost-benefit analysis module (maintenance cost vs. downtime cost optimization)

---

## License

MIT

---

*Built as a portfolio project demonstrating senior-level data engineering practices for industrial predictive maintenance in the Australian mining sector.*
