# Databricks notebook source
# MAGIC %md
# MAGIC # Create (or reuse) UC schema & volume for Knowledge Assistant
# MAGIC
# MAGIC This notebook creates a Unity Catalog schema and volume, and prints the
# MAGIC volume path we'll store markdown files in.

# COMMAND ----------

dbutils.widgets.text("catalog", "main", "catalog")
dbutils.widgets.text("schema", "ab_demo", "schema")
dbutils.widgets.text("volume", "ka_data", "volume")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
volume = dbutils.widgets.get("volume")

print(f"Target UC objects => catalog={catalog}, schema={schema}, volume={volume}")

# Create schema & volume (best effort—ignore if you lack perms to create the catalog)
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.{volume}")

volume_dir = f"/Volumes/{catalog}/{schema}/{volume}"
knowledge_dir = f"{volume_dir}/knowledge"
print("Volume dir:", volume_dir)
print("Knowledge dir:", knowledge_dir)

# Ensure directories exist
dbutils.fs.mkdirs(knowledge_dir)

# COMMAND ----------

# MAGIC %md
# MAGIC Next: Run `02_load_sample_docs_to_volume.py`.
