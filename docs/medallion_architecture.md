# Medallion Architecture — Design Decisions

## Why Medallion? (vs. Lambda, vs. Plain ETL)

### Medallion (Bronze → Silver → Gold)
A layered data quality architecture where each layer adds incremental value. Data flows linearly through progressively refined stages.

### Why not Lambda Architecture?
Lambda maintains parallel batch and streaming paths that must produce consistent results — this operational complexity is unjustified for a single-source sensor pipeline. Medallion achieves the same goal (raw preservation + refined outputs) without duplicated logic.

### Why not plain ETL (source → target)?
Plain ETL loses the raw data. When a data quality rule changes or a feature engineering approach is revised, there's no way to reprocess from source. Medallion's Bronze layer is an immutable audit trail — we can always recompute Silver and Gold from Bronze without re-ingesting from upstream systems. In mining operations, regulatory audits can request the original sensor readings that informed a maintenance decision made months ago.

### Summary

| Pattern | Raw Preservation | Incremental Quality | Operational Complexity | Auditability |
|---------|:---:|:---:|:---:|:---:|
| **Medallion** | Yes | Yes | Low | Full |
| Lambda | Yes | Partial | High | Partial |
| Plain ETL | No | No | Low | None |

---

## Why Delta Lake?

Delta Lake was chosen over raw Parquet, Iceberg, and Hudi for this pipeline:

### ACID Transactions
Sensor telemetry writes must be atomic. A partial write (e.g., half a streaming batch) would create corrupt data that silently propagates downstream. Delta's transaction log guarantees all-or-nothing writes.

### Schema Enforcement & Evolution
Mining equipment sensor configurations change during overhauls — a maintenance crew might replace a temperature sensor with a higher-precision model that reports an additional decimal place, or add a new vibration channel. Delta's schema enforcement catches unexpected changes at write time, while `mergeSchema` allows controlled evolution.

### Time Travel
Delta's versioning enables:
- **Debugging:** "What did the Silver table look like when the model was trained last Tuesday?"
- **Reproducibility:** Pin ML training to a specific table version for audit compliance
- **Rollback:** Revert a bad quality rule change without re-running the entire pipeline

### MERGE (Upsert)
The MERGE operation on `(unit_id, cycle)` is the foundation of idempotent pipeline runs. Network failures, cluster preemptions, and notebook timeouts are common in cloud environments — every notebook can be safely re-run without creating duplicate records.

### Z-ORDER
Co-locates data by `unit_id` on disk, making ML training queries that filter by unit 5–10x faster on large datasets.

---

## Bronze Layer Design Decisions

**Purpose:** Immutable landing zone for raw sensor telemetry.

| Decision | Rationale |
|----------|-----------|
| **Explicit schema (`StructType`)** | Prevents silent data corruption from upstream changes. Catches sensor configuration changes during equipment overhauls. |
| **MERGE for idempotency** | Safe re-processing without duplicates. Critical for pipeline recovery after failures. |
| **Auto Loader (cloudFiles)** | Incremental file ingestion with checkpointing. Only processes new files each run, enabling near-real-time ingestion. |
| **Metadata columns** | `_ingestion_timestamp`, `_source_file`, `_pipeline_version` provide full lineage. Mining regulatory audits require provenance of all data used in maintenance decisions. |
| **Partition by `_ingestion_date`** | Enables efficient time-range queries and simplifies data retention policies. |
| **No transformations** | Bronze is raw — no cleaning, no filtering, no enrichment. This preserves the original signal for reprocessing when quality rules evolve. |

---

## Silver Layer Design Decisions

**Purpose:** Quality-assured data with drift detection and anomaly flagging.

| Decision | Rationale |
|----------|-----------|
| **Rolling z-score drift detection** | Industrial sensors degrade over time. A thermocouple drifting out of calibration produces readings that are technically in-range but statistically anomalous. Static bounds miss this; rolling z-scores catch gradual drift. |
| **Window=20, z_threshold=3.0** | Window=20 cycles ≈ one maintenance rotation in mining. z=3.0 gives 0.3% false positive rate under normality — tight enough to catch real drift, loose enough to avoid alert fatigue. |
| **Quality metrics to separate Delta table** | Decouples quality observability from data flow. Enables a standalone quality dashboard without touching the main pipeline. Quality trends over time (e.g., "s3 drift detections increased 40% this month") trigger proactive sensor recalibration. |
| **Filter, don't repair** | Flagged records are excluded from Silver rather than imputed. In safety-critical mining decisions, a missing reading is better than a fabricated one. Original readings remain in Bronze for investigation. |
| **Overwrite with schema merge** | Full refresh with `mergeSchema=true` supports schema evolution while maintaining Delta time travel history for rollback. |

---

## Gold Layer Design Decisions

**Purpose:** Engineered feature table optimized for RUL prediction.

| Decision | Rationale |
|----------|-----------|
| **RUL cap at 125 cycles** | Equipment in early life behaves identically regardless of whether RUL is 200 or 300. Capping creates a piece-wise linear target: flat during healthy operation, linearly decreasing during degradation. This focuses model capacity on the prediction window that matters for maintenance scheduling. |
| **Rolling windows [5, 10, 20]** | Multiple window sizes capture different operational timescales. Window=5 ≈ one shift, window=10 ≈ half a maintenance cycle, window=20 ≈ full rotation. These are consistently the highest-importance features in RUL prediction. |
| **5 stats per window (mean, std, min, max, range)** | Mean captures trend; std captures volatility increase near failure; min/max capture extreme excursions; range captures widening operating envelope — a classic degradation signature. |
| **Lag features [1, 5, 10]** | Capture temporal dynamics — how quickly a sensor is changing. Lag-1 = immediate change; lag-5 = shift-over-shift; lag-10 = weekly comparison. |
| **Rate of change (first difference)** | Acceleration of degradation. A sensor that's not just drifting but drifting *faster* is a stronger failure predictor than absolute value alone. |
| **Z-ORDER on unit_id** | ML training queries filter by unit (train/val split). Z-ORDER co-locates all readings for one unit, reducing I/O by 5–10x on large feature tables. |
| **Unit-partitioned computation** | All rolling, lag, and RoC features are computed within each unit's time series. Cross-unit contamination would introduce data leakage — unit 42's sensor history has no bearing on unit 17's degradation. |

---

## Trade-offs Considered

### 1. Pandas vs. PySpark for Feature Engineering

**Chose:** Pandas in `src/` modules, PySpark in notebooks.

**Trade-off:** Pandas is simpler to test, debug, and develop locally. PySpark scales to billions of rows. The dual implementation lets us develop and test locally with Pandas, then use the same logic via `toPandas()` on Databricks for datasets that fit in driver memory (FD001 at 20K rows easily fits). For production scale, the PySpark equivalents in `notebooks/03` handle the same transforms natively.

### 2. Custom Quality Checks vs. Great Expectations

**Chose:** Custom Python module (`src/data_quality.py`).

**Trade-off:** Great Expectations provides a declarative framework with rich reporting, but adds significant dependency weight and requires its own configuration management. For a focused pipeline with 3 specific checks (drift, frequency, op mode), custom code is more transparent, testable, and demonstrates deeper understanding of the domain to portfolio reviewers.

### 3. XGBoost vs. Deep Learning (LSTM/Transformer)

**Chose:** XGBoost regressor.

**Trade-off:** LSTMs and Transformers can model temporal sequences directly without manual feature engineering. However, XGBoost with engineered features (rolling stats, lags) consistently matches or exceeds deep learning performance on C-MAPSS while being 100x faster to train, fully interpretable via feature importance, and deployable without GPU infrastructure — critical for edge deployment on mine-site telematics.

### 4. Unit-based vs. Random Train/Val Split

**Chose:** Split by engine unit (80/20 units).

**Trade-off:** Random splitting yields higher reported metrics (R² > 0.95) because the model sees correlated readings from the same engine in both train and validation sets. This is **temporal data leakage** — in production, we never have future data from an engine we're predicting. Unit-based splitting gives honest metrics (R² ≈ 0.80–0.90) that reflect real-world deployment performance.

---

## Scale Considerations

### Current State: 1 Fleet, 100 Units, ~20K Readings

The FD001 dataset fits comfortably in a single Pandas DataFrame on a laptop. All operations complete in seconds.

### Near-term Scale: 1 Mine Site, 500 Units, 10M Readings/Month

| Component | Change Required |
|-----------|----------------|
| Ingestion | Auto Loader handles incremental file growth automatically |
| Bronze/Silver | PySpark window functions replace Pandas groupby.transform |
| Gold | Feature computation in PySpark; Z-ORDER and OPTIMIZE become load-bearing |
| ML Training | XGBoost `n_jobs=-1` parallelizes across cluster cores |
| Dashboard | Add server-side pagination; consider Databricks SQL dashboard |

### Long-term Scale: Multi-site Mining Operation, 5000+ Units, 1B+ Readings/Year

| Component | Change Required |
|-----------|----------------|
| Ingestion | Azure Event Hubs / Kafka for real-time streaming |
| Storage | Unity Catalog cross-site federation with site-level catalogs |
| Compute | Dedicated Databricks clusters per site with shared model registry |
| ML | Site-specific fine-tuning with transfer learning from base model |
| Governance | Row-level security by site; column-level masking for proprietary sensor configs |
| Orchestration | Databricks Workflows with SLA monitoring and PagerDuty alerting |
| Edge | ONNX model export to on-truck telematics (Caterpillar MineStar, Komatsu FrontRunner) |

The Medallion architecture scales linearly — adding sites means adding catalogs, not redesigning the pipeline. Each layer's contract (Bronze = raw, Silver = validated, Gold = ML-ready) remains unchanged regardless of data volume.
