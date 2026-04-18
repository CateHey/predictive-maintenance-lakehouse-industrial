# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # 04 — Model Training with MLflow
# MAGIC
# MAGIC Trains an XGBoost regressor on the Gold feature table to predict
# MAGIC Remaining Useful Life (RUL). Uses unit-aware train/validation splitting
# MAGIC to prevent data leakage.
# MAGIC
# MAGIC **Model Registry Name:** `rul_xgboost_fd001`

# COMMAND ----------

import mlflow
import mlflow.xgboost
import numpy as np
import xgboost as xgb
from pyspark.sql import SparkSession
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# COMMAND ----------

spark = SparkSession.builder.getOrCreate()
mlflow.set_experiment("/Shared/predictive_maintenance/rul_experiment")

GOLD_PATH = "/FileStore/predictive_maintenance/gold/feature_table"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load Gold Feature Table

# COMMAND ----------

gold_df = spark.read.format("delta").load(GOLD_PATH)
pdf = gold_df.toPandas()

print(f"Total records: {len(pdf)}")
print(f"Total features: {len(pdf.columns)}")
print(f"Units: {pdf['unit_id'].nunique()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Train/Validation Split by Unit
# MAGIC
# MAGIC Splitting by unit prevents temporal data leakage — no readings from
# MAGIC the same equipment appear in both train and validation sets.

# COMMAND ----------

unique_units = pdf["unit_id"].unique()
np.random.seed(42)
np.random.shuffle(unique_units)

split_idx = int(len(unique_units) * 0.8)
train_units = unique_units[:split_idx]
val_units = unique_units[split_idx:]

train_df = pdf[pdf["unit_id"].isin(train_units)]
val_df = pdf[pdf["unit_id"].isin(val_units)]

print(f"Train: {len(train_df)} records ({len(train_units)} units)")
print(f"Validation: {len(val_df)} records ({len(val_units)} units)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Prepare Features

# COMMAND ----------

EXCLUDE_COLS = [
    "unit_id", "cycle", "rul",
    "_ingestion_timestamp", "_source_file", "_pipeline_version",
    "_silver_timestamp", "_gold_timestamp",
]

feature_cols = [c for c in pdf.columns if c not in EXCLUDE_COLS]

X_train = train_df[feature_cols].values
y_train = train_df["rul"].values
X_val = val_df[feature_cols].values
y_val = val_df["rul"].values

print(f"Feature count: {len(feature_cols)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Train XGBoost with MLflow Tracking

# COMMAND ----------

mlflow.xgboost.autolog(log_models=True)

PARAMS = {
    "n_estimators": 200,
    "max_depth": 6,
    "learning_rate": 0.1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": 42,
    "n_jobs": -1,
}

with mlflow.start_run(run_name="xgboost_rul_fd001") as run:
    mlflow.log_params({
        "train_units": len(train_units),
        "val_units": len(val_units),
        "feature_count": len(feature_cols),
        "max_rul_cap": 125,
        "dataset": "NASA_CMAPSS_FD001",
        "split_strategy": "by_unit",
    })

    model = xgb.XGBRegressor(**PARAMS)
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )

    y_pred = model.predict(X_val)

    rmse = float(np.sqrt(mean_squared_error(y_val, y_pred)))
    mae = float(mean_absolute_error(y_val, y_pred))
    r2 = float(r2_score(y_val, y_pred))

    mlflow.log_metrics({"val_rmse": rmse, "val_mae": mae, "val_r2": r2})

    print(f"Validation RMSE: {rmse:.2f}")
    print(f"Validation MAE:  {mae:.2f}")
    print(f"Validation R²:   {r2:.4f}")

    run_id = run.info.run_id
    print(f"MLflow Run ID: {run_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Feature Importance

# COMMAND ----------

import pandas as pd

importance_df = pd.DataFrame({
    "feature": feature_cols,
    "importance": model.feature_importances_,
}).sort_values("importance", ascending=False)

print("Top 15 features:")
display(spark.createDataFrame(importance_df.head(15)))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Register Model

# COMMAND ----------

model_uri = f"runs:/{run_id}/model"
model_name = "rul_xgboost_fd001"

registered_model = mlflow.register_model(model_uri, model_name)
print(f"Model registered: {model_name}, version {registered_model.version}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Prediction Distribution Analysis

# COMMAND ----------

pred_df = pd.DataFrame({"actual_rul": y_val, "predicted_rul": y_pred})
pred_df["residual"] = pred_df["actual_rul"] - pred_df["predicted_rul"]
pred_df["abs_error"] = pred_df["residual"].abs()

print("Prediction error distribution:")
display(spark.createDataFrame(pred_df.describe().reset_index()))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Risk Classification
# MAGIC
# MAGIC Classify units by predicted RUL for operational decision-making.

# COMMAND ----------

val_predictions = val_df[["unit_id", "cycle"]].copy()
val_predictions["predicted_rul"] = y_pred
val_predictions["actual_rul"] = y_val

latest_per_unit = val_predictions.sort_values("cycle").groupby("unit_id").last().reset_index()
latest_per_unit["risk_level"] = pd.cut(
    latest_per_unit["predicted_rul"],
    bins=[-1, 50, 100, float("inf")],
    labels=["CRITICAL", "WARNING", "HEALTHY"],
)

print("Risk distribution:")
print(latest_per_unit["risk_level"].value_counts())
display(spark.createDataFrame(latest_per_unit))
