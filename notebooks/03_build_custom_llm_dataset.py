# Databricks notebook source
# MAGIC %md
# MAGIC # Create a tiny labeled dataset for Custom LLM
# MAGIC
# MAGIC This creates `(request, response)` pairs you can feed to Agent Bricks: Custom LLM.

# COMMAND ----------

dbutils.widgets.text("catalog", "main", "catalog")
dbutils.widgets.text("schema", "ab_demo", "schema")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

table_name = f"{catalog}.{schema}.custom_llm_tiny"

data = [
    ("Ticket: 'Refund not issued after return' → classify: Billing/Shipping/Tech", "Billing"),
    ("Ticket: 'Where is my package? tracking shows stuck' → classify", "Shipping"),
    ("Ticket: 'App crashes when uploading photo' → classify", "Tech"),
    ("Ticket: 'Promo code not applied at checkout' → classify", "Billing"),
    ("Ticket: 'Damaged item arrived, need replacement' → classify", "Shipping"),
    ("Ticket: 'Two‑factor login not working' → classify", "Tech"),
]

df = spark.createDataFrame(data, ["request", "response"])
df.write.mode("overwrite").saveAsTable(table_name)

print("Wrote labeled rows to:", table_name)
display(spark.table(table_name).limit(10))

# COMMAND ----------

# MAGIC %md
# MAGIC In the UI, open **Agents → Custom LLM** and select this table as a dataset.
