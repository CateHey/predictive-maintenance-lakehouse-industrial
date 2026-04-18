# Medallion Architecture — Design Decisions

## Overview

This document captures the architectural decisions behind the three-layer Medallion pipeline for industrial predictive maintenance telemetry.

## Layer Design

### Bronze (Raw Ingestion)

**Purpose:** Immutable landing zone for raw sensor telemetry.

**Key decisions:**
- **Schema enforcement on read:** Explicit `StructType` definition prevents silent schema drift from upstream data sources. In mining operations, sensor configurations change during equipment overhauls — schema enforcement catches these changes immediately rather than propagating bad data downstream.
- **MERGE for idempotency:** The Bronze layer uses Delta MERGE on `(unit_id, cycle)` to enable safe re-processing without record duplication. This is critical for pipeline recovery — if a streaming batch fails mid-write, the entire notebook can be safely re-run.
- **Metadata columns:** Every record is enriched with `_ingestion_timestamp`, `_source_file`, and `_pipeline_version` for full lineage tracking. Mining regulatory audits require provenance of all data used in maintenance decisions.

### Silver (Validated & Cleansed)

**Purpose:** Quality-assured data with drift detection and range validation applied.

**Key decisions:**
- **Rolling z-score drift detection:** Industrial sensors degrade over time — a thermocouple drifting out of calibration produces readings that are technically valid but statistically anomalous. The rolling z-score approach (window=20, threshold=3.0) detects gradual drift that static range checks miss.
- **Quality metrics logging to Delta:** All quality check results are persisted to a separate Delta table. This creates an auditable quality history that can be dashboarded separately and used to trigger recalibration work orders.
- **Non-destructive validation:** Out-of-range and drifted readings are flagged but not dropped in Silver. Downstream consumers (Gold, ML models) decide how to handle flagged data. This preserves maximum information while making quality issues visible.

### Gold (ML-Ready Features)

**Purpose:** Engineered feature table optimized for RUL prediction.

**Key decisions:**
- **RUL cap at 125 cycles:** Equipment in early life (high RUL) behaves identically regardless of whether it has 200 or 300 cycles remaining. Capping prevents the model from wasting capacity learning to distinguish between "very healthy" states. The 125 threshold is a standard in turbofan degradation literature and maps well to mining equipment maintenance windows.
- **Rolling statistics (windows 5, 10, 20):** Multiple window sizes capture both short-term transients (window=5, ~1 shift in mining) and medium-term trends (window=20, ~1 week of daily readings). These are the highest-importance features for RUL prediction.
- **Lag features:** Capture temporal dynamics — how sensor values evolve relative to their recent history. Lag-1 captures immediate change; lag-10 captures weekly patterns.
- **Unit-aware operations:** All rolling and lag computations are partitioned by `unit_id` to prevent cross-contamination between equipment units.

## Unity Catalog Structure

```
mining_ops                          (catalog)
└── predictive_maintenance          (schema)
    ├── bronze_sensor_readings      (table)
    ├── silver_sensor_readings      (table)
    ├── silver_quality_metrics      (table)
    ├── gold_feature_table          (table)
    └── models/                     (registered models)
        └── rul_xgboost_fd001
```

**Rationale:** The three-level namespace (`catalog.schema.table`) mirrors the organizational structure of a mining operation:
- **Catalog** = business unit (mining operations)
- **Schema** = use case (predictive maintenance)
- **Table** = data asset

This enables fine-grained access control — maintenance engineers can access Gold tables without seeing raw telemetry, while data engineers have full access across all layers.

## Data Flow Guarantees

| Property | Implementation |
|----------|---------------|
| **Idempotency** | Delta MERGE on natural keys at every layer |
| **Schema evolution** | Explicit schemas + `overwriteSchema` on initial writes |
| **Lineage** | Metadata columns + Delta table history |
| **Quality visibility** | Separate quality metrics table with per-run logging |
| **Reproducibility** | MLflow experiment tracking with full parameter capture |

## Trade-offs & Limitations

1. **Batch vs. streaming:** This implementation uses batch processing (read all → write all). A production system would use Structured Streaming with Auto Loader for true real-time ingestion. The batch approach was chosen to work within Databricks Community Edition compute constraints.

2. **Single fault mode:** FD001 contains one operating condition and one fault mode. Real mining equipment exhibits multiple failure modes (bearing wear, thermal degradation, vibration-induced fatigue). The architecture supports multi-fault extension by adding fault-mode columns and model ensembles.

3. **Local Delta vs. cloud Delta:** Local development uses `deltalake` (Python). Databricks uses the full Delta Lake engine with Z-ordering, OPTIMIZE, and VACUUM. The pipeline code is portable between environments.
