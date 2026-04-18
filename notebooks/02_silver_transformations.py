# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # 02 — Silver Transformations
# MAGIC
# MAGIC Applies data quality checks, logs quality metrics, and writes validated records
# MAGIC to the Silver Delta table.
# MAGIC
# MAGIC **Medallion Layer:** Silver (cleansed, validated)
# MAGIC
# MAGIC **Unity Catalog Path:** `mining_ops.predictive_maintenance.silver_sensor_readings`

# COMMAND ----------

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    current_timestamp,
    lit,
    mean,
    stddev,
    abs as spark_abs,
    when,
)
from delta.tables import DeltaTable

# COMMAND ----------

spark = SparkSession.builder.getOrCreate()

BRONZE_PATH = "/FileStore/predictive_maintenance/bronze/sensor_readings"
SILVER_PATH = "/FileStore/predictive_maintenance/silver/sensor_readings"
QUALITY_LOG_PATH = "/FileStore/predictive_maintenance/silver/quality_metrics"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Read Bronze

# COMMAND ----------

bronze_df = spark.read.format("delta").load(BRONZE_PATH)
print(f"Bronze records loaded: {bronze_df.count()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Data Quality Checks
# MAGIC
# MAGIC ### 1. Null Check — Drop records with null sensor values

# COMMAND ----------

SENSOR_COLS = [f"sensor_{i}" for i in range(1, 22)]

non_null_df = bronze_df.dropna(subset=SENSOR_COLS)
null_count = bronze_df.count() - non_null_df.count()
print(f"Records dropped (nulls): {null_count}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 2. Range Validation — Flag out-of-range sensor readings

# COMMAND ----------

SENSOR_BOUNDS = {
    "sensor_2": (640.0, 645.0),
    "sensor_3": (1570.0, 1620.0),
    "sensor_4": (1380.0, 1420.0),
    "sensor_7": (549.0, 556.0),
    "sensor_11": (47.0, 49.0),
    "sensor_12": (520.0, 525.0),
    "sensor_15": (8.4, 8.8),
    "sensor_20": (38.5, 39.5),
    "sensor_21": (23.2, 23.6),
}

validated_df = non_null_df
range_violation_counts = {}

for sensor, (lower, upper) in SENSOR_BOUNDS.items():
    violation_flag = f"_{sensor}_oor"
    validated_df = validated_df.withColumn(
        violation_flag,
        when((col(sensor) < lower) | (col(sensor) > upper), lit(True)).otherwise(lit(False)),
    )
    oor_count = validated_df.filter(col(violation_flag)).count()
    range_violation_counts[sensor] = oor_count

print("Range violations per sensor:")
for sensor, count in range_violation_counts.items():
    if count > 0:
        print(f"  {sensor}: {count}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3. Drift Detection — Rolling Z-score per unit

# COMMAND ----------

from pyspark.sql.window import Window

DRIFT_SENSORS = ["sensor_2", "sensor_3", "sensor_4", "sensor_11", "sensor_15"]
DRIFT_THRESHOLD = 3.0
WINDOW_SIZE = 20

unit_cycle_window = Window.partitionBy("unit_id").orderBy("cycle").rowsBetween(-WINDOW_SIZE, 0)

drift_df = validated_df
for sensor in DRIFT_SENSORS:
    rolling_avg = mean(col(sensor)).over(unit_cycle_window)
    rolling_sd = stddev(col(sensor)).over(unit_cycle_window)

    drift_df = drift_df.withColumn(
        f"_{sensor}_zscore",
        when(rolling_sd > 0, spark_abs((col(sensor) - rolling_avg) / rolling_sd)).otherwise(0.0),
    )
    drift_df = drift_df.withColumn(
        f"_{sensor}_drift",
        when(col(f"_{sensor}_zscore") > DRIFT_THRESHOLD, lit(True)).otherwise(lit(False)),
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Log Quality Metrics to Delta

# COMMAND ----------

from pyspark.sql import Row

quality_rows = [
    Row(
        check_name="null_records_dropped",
        value=float(null_count),
        run_timestamp=str(current_timestamp()),
    ),
] + [
    Row(
        check_name=f"range_violations_{sensor}",
        value=float(count),
        run_timestamp=str(current_timestamp()),
    )
    for sensor, count in range_violation_counts.items()
]

quality_df = spark.createDataFrame(quality_rows)
quality_df.write.format("delta").mode("append").save(QUALITY_LOG_PATH)
print("Quality metrics logged.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write Silver Delta
# MAGIC
# MAGIC Drop internal quality flag columns before writing the clean table.

# COMMAND ----------

internal_cols = [c for c in drift_df.columns if c.startswith("_") and c != "_ingestion_timestamp"]
silver_df = drift_df.drop(*internal_cols)

silver_df = silver_df.withColumn("_silver_timestamp", current_timestamp())

if DeltaTable.isDeltaTable(spark, SILVER_PATH):
    silver_table = DeltaTable.forPath(spark, SILVER_PATH)
    (
        silver_table.alias("target")
        .merge(
            silver_df.alias("source"),
            "target.unit_id = source.unit_id AND target.cycle = source.cycle",
        )
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )
    print("Silver MERGE complete.")
else:
    silver_df.write.format("delta").mode("overwrite").save(SILVER_PATH)
    print("Initial Silver table created.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verification

# COMMAND ----------

result_df = spark.read.format("delta").load(SILVER_PATH)
print(f"Silver table record count: {result_df.count()}")
print(f"Unique units: {result_df.select('unit_id').distinct().count()}")
display(result_df.limit(5))
