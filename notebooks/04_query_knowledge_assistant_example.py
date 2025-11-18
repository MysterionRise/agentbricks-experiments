# Databricks notebook source
# MAGIC %md
# MAGIC # Query a Knowledge Assistant endpoint (template)
# MAGIC
# MAGIC After you create your KA agent in the UI and it finishes building, copy the
# MAGIC endpoint name here and try a simple question.
# MAGIC
# MAGIC Note: Databricks recommends using the **Get code** button in AI Playground to
# MAGIC copy the official Python snippet for your endpoint. Payload shapes may change.

# COMMAND ----------

# %pip install mlflow

import os
import mlflow
from mlflow.deployments import get_deploy_client

# Create widget with default value
dbutils.widgets.text("endpoint_name", "REPLACE_WITH_YOUR_KA_ENDPOINT", "endpoint_name")
ENDPOINT_NAME = dbutils.widgets.get("endpoint_name")

QUESTION = "What does the FEMA basics doc recommend for households?"

client = get_deploy_client("databricks")
try:
    # Many KA endpoints accept a chat-style payload; confirm via Playground → Get code
    resp = client.predict(
        endpoint=ENDPOINT_NAME,
        inputs={
            "messages": [
                {"role": "user", "content": QUESTION}
            ]
        },
    )
    print(resp)
except Exception as e:
    print("If this fails, open AI Playground → Get code → Python, and paste the exact snippet here.")
    print("Error:", repr(e))

# COMMAND ----------

# MAGIC %md
# MAGIC You should see a grounded answer with citations to the docs you ingested.
