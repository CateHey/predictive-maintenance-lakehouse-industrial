# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # 01 — Bronze Ingestion
# MAGIC
# MAGIC Reads streaming JSON batches from the simulator and writes to the Bronze Delta table
# MAGIC with schema enforcement and idempotent MERGE logic.
# MAGIC
# MAGIC **Medallion Layer:** Bronze (raw, append-only)
# MAGIC
# MAGIC **Unity Catalog Path:** `mining_ops.predictive_maintenance.bronze_sensor_readings`

# COMMAND ----------

from pyspark.sql import SparkSession
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StructField,
    StructType,
)
from pyspark.sql.functions import current_timestamp, input_file_name, lit
from delta.tables import DeltaTable

# COMMAND ----------

spark = SparkSession.builder.getOrCreate()

STREAMING_PATH = "/FileStore/predictive_maintenance/streaming/"
BRONZE_PATH = "/FileStore/predictive_maintenance/bronze/sensor_readings"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Schema Definition
# MAGIC Explicit schema enforcement prevents silent data corruption from upstream changes.

# COMMAND ----------

SENSOR_SCHEMA = StructType([
    StructField("unit_id", IntegerType(), nullable=False),
    StructField("cycle", IntegerType(), nullable=False),
    StructField("op_setting_1", DoubleType(), nullable=True),
    StructField("op_setting_2", DoubleType(), nullable=True),
    StructField("op_setting_3", DoubleType(), nullable=True),
    *[StructField(f"sensor_{i}", DoubleType(), nullable=True) for i in range(1, 22)],
])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Read Streaming JSON Batches

# COMMAND ----------

raw_df = (
    spark.read
    .schema(SENSOR_SCHEMA)
    .option("multiLine", True)
    .json(STREAMING_PATH)
)

raw_df = (
    raw_df
    .withColumn("_ingestion_timestamp", current_timestamp())
    .withColumn("_source_file", input_file_name())
    .withColumn("_pipeline_version", lit("1.0.0"))
)

print(f"Records read: {raw_df.count()}")
raw_df.printSchema()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write to Bronze Delta with MERGE (Idempotent)
# MAGIC
# MAGIC MERGE on (unit_id, cycle) ensures re-running the notebook does not duplicate records.

# COMMAND ----------

if DeltaTable.isDeltaTable(spark, BRONZE_PATH):
    bronze_table = DeltaTable.forPath(spark, BRONZE_PATH)

    (
        bronze_table.alias("target")
        .merge(
            raw_df.alias("source"),
            "target.unit_id = source.unit_id AND target.cycle = source.cycle"
        )
        .whenNotMatchedInsertAll()
        .execute()
    )
    print("MERGE complete — new records inserted, duplicates skipped.")
else:
    (
        raw_df.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .save(BRONZE_PATH)
    )
    print("Initial Bronze table created.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verification

# COMMAND ----------

bronze_df = spark.read.format("delta").load(BRONZE_PATH)
print(f"Bronze table record count: {bronze_df.count()}")
print(f"Unique units: {bronze_df.select('unit_id').distinct().count()}")
display(bronze_df.describe())

# COMMAND ----------

# MAGIC %md
# MAGIC ## Delta Table History
# MAGIC Audit trail for all writes — critical for data governance in mining operations.

# COMMAND ----------

delta_table = DeltaTable.forPath(spark, BRONZE_PATH)
display(delta_table.history())
