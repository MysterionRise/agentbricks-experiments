# Databricks notebook source
# MAGIC %md
# MAGIC # Agent Bricks demo: quick preflight
# MAGIC
# MAGIC This notebook prints basic workspace info and checks for the presence of the
# MAGIC embedding endpoint `databricks-gte-large-en`, which Knowledge Assistant
# MAGIC uses when configured with Vector Search. If the endpoint is missing or
# MAGIC restricted, follow workspace docs to enable Mosaic AI Model Serving and to
# MAGIC disable guardrails & rate limits on that embedding endpoint (when required).

# COMMAND ----------

# If needed:
# %pip install databricks-sdk

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
print("Workspace host:", w.config.host)

try:
    # This endpoint name is referenced in Databricks docs.
    ep = w.serving_endpoints.get(name="databricks-gte-large-en")
    print("Found embedding endpoint:", ep.name, "| Ready state:", getattr(ep.state, "ready", None))
except Exception as e:
    print("Embedding endpoint 'databricks-gte-large-en' not found or not accessible.")
    print("You can still proceed with Knowledge Assistant using UC Files as the knowledge source.")

# Helpful context where possible
import os
print("User:", os.getenv("USER") or "n/a")
try:
    cloud = spark.conf.get("spark.databricks.clusterUsageTags.cloudProvider")
    print("Cloud provider:", cloud)
except Exception:
    pass

# COMMAND ----------

# MAGIC %md
# MAGIC Next: Run `01_setup_catalog_schema_volume.py`.
