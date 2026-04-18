# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # 03 — Gold Feature Engineering
# MAGIC
# MAGIC Computes rolling statistics, lag features, rate-of-change, and RUL labels
# MAGIC to produce an ML-ready Gold table.
# MAGIC
# MAGIC **Medallion Layer:** Gold (ML-ready, business-level)
# MAGIC
# MAGIC **Unity Catalog Path:** `mining_ops.predictive_maintenance.gold_feature_table`

# COMMAND ----------

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    current_timestamp,
    lag,
    lit,
    max as spark_max,
    mean,
    stddev,
    when,
)
from pyspark.sql.window import Window
from delta.tables import DeltaTable

# COMMAND ----------

spark = SparkSession.builder.getOrCreate()

SILVER_PATH = "/FileStore/predictive_maintenance/silver/sensor_readings"
GOLD_PATH = "/FileStore/predictive_maintenance/gold/feature_table"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Read Silver

# COMMAND ----------

silver_df = spark.read.format("delta").load(SILVER_PATH)
print(f"Silver records loaded: {silver_df.count()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Compute RUL Labels
# MAGIC
# MAGIC RUL = max_cycle - current_cycle, capped at 125 to prevent the model
# MAGIC from overfitting on early-life (healthy) patterns.

# COMMAND ----------

max_cycle_df = silver_df.groupBy("unit_id").agg(spark_max("cycle").alias("max_cycle"))
gold_df = silver_df.join(max_cycle_df, on="unit_id")
gold_df = gold_df.withColumn("rul", col("max_cycle") - col("cycle"))
gold_df = gold_df.withColumn("rul", when(col("rul") > 125, 125).otherwise(col("rul")))
gold_df = gold_df.drop("max_cycle")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Rolling Sensor Statistics

# COMMAND ----------

SENSOR_COLS = [f"sensor_{i}" for i in range(1, 22)]
WINDOW_SIZES = [5, 10, 20]

for window_size in WINDOW_SIZES:
    w = Window.partitionBy("unit_id").orderBy("cycle").rowsBetween(-window_size + 1, 0)
    for sensor in SENSOR_COLS:
        gold_df = gold_df.withColumn(f"{sensor}_rolling_mean_{window_size}", mean(col(sensor)).over(w))
        gold_df = gold_df.withColumn(f"{sensor}_rolling_std_{window_size}", stddev(col(sensor)).over(w))

print(f"Rolling stats computed for {len(SENSOR_COLS)} sensors × {len(WINDOW_SIZES)} windows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Lag Features

# COMMAND ----------

LAGS = [1, 5, 10]
unit_window = Window.partitionBy("unit_id").orderBy("cycle")

for lag_val in LAGS:
    for sensor in SENSOR_COLS:
        gold_df = gold_df.withColumn(f"{sensor}_lag_{lag_val}", lag(col(sensor), lag_val).over(unit_window))

print(f"Lag features computed: {len(SENSOR_COLS)} sensors × {len(LAGS)} lags")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Rate of Change Features

# COMMAND ----------

for sensor in SENSOR_COLS:
    gold_df = gold_df.withColumn(
        f"{sensor}_roc",
        col(sensor) - lag(col(sensor), 1).over(unit_window),
    )

print(f"Rate-of-change features: {len(SENSOR_COLS)} columns")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Drop NaN Rows & Add Metadata

# COMMAND ----------

gold_df = gold_df.na.drop()
gold_df = gold_df.withColumn("_gold_timestamp", current_timestamp())

print(f"Gold feature table: {gold_df.count()} records, {len(gold_df.columns)} columns")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write Gold Delta

# COMMAND ----------

if DeltaTable.isDeltaTable(spark, GOLD_PATH):
    gold_table = DeltaTable.forPath(spark, GOLD_PATH)
    (
        gold_table.alias("target")
        .merge(
            gold_df.alias("source"),
            "target.unit_id = source.unit_id AND target.cycle = source.cycle",
        )
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )
    print("Gold MERGE complete.")
else:
    gold_df.write.format("delta").mode("overwrite").save(GOLD_PATH)
    print("Initial Gold table created.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verification & Summary Statistics

# COMMAND ----------

result_df = spark.read.format("delta").load(GOLD_PATH)
print(f"Gold table record count: {result_df.count()}")
print(f"Feature columns: {len(result_df.columns)}")
print(f"RUL distribution:")
display(result_df.select("rul").describe())

# COMMAND ----------

# MAGIC %md
# MAGIC ## Per-Unit Aggregation Summary

# COMMAND ----------

from pyspark.sql.functions import min as spark_min, avg as spark_avg, count as spark_count

unit_summary = (
    result_df.groupBy("unit_id")
    .agg(
        spark_count("cycle").alias("total_cycles"),
        spark_min("rul").alias("min_rul"),
        spark_avg("rul").alias("avg_rul"),
        spark_avg("sensor_2").alias("avg_sensor_2"),
        spark_avg("sensor_3").alias("avg_sensor_3"),
        spark_avg("sensor_4").alias("avg_sensor_4"),
    )
    .orderBy("unit_id")
)
display(unit_summary)
