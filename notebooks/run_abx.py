# Databricks notebook source
# MAGIC %md
# MAGIC # Run `abx` from a notebook
# MAGIC
# MAGIC Thin wrapper for people who prefer the notebook UI over the CLI or the
# MAGIC Asset Bundle. It installs the package from this repo and calls the same
# MAGIC entry point the jobs use. Pick the command with the widget and run all.
# MAGIC
# MAGIC Commands: `validate` (offline), `setup`, `deploy`, `eval`, `cost`.

# COMMAND ----------

# MAGIC %pip install -q -e .. databricks-agents>=1.0
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.dropdown("command", "validate", ["validate", "setup", "deploy", "eval", "cost"])
dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema", "ab_demo")
dbutils.widgets.text("sql_warehouse_id", "")

command = dbutils.widgets.get("command")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
warehouse = dbutils.widgets.get("sql_warehouse_id")

# COMMAND ----------

import os

from abx.cli import main

repo_root = os.path.abspath("..")
argv = ["--set", f"ABX_CATALOG={catalog}", "--set", f"ABX_SCHEMA={schema}"]
if warehouse:
    argv += ["--set", f"ABX_SQL_WAREHOUSE_ID={warehouse}"]
argv.append(command)
if command in ("validate", "setup"):
    argv += ["--corpus", f"{repo_root}/data/corpus"]
if command in ("validate", "eval"):
    argv += ["--seed", f"{repo_root}/evals/seed.jsonl", "--pyproject", f"{repo_root}/pyproject.toml"]
if command in ("eval", "cost"):
    argv += ["--out", "/tmp/abx-reports"]

exit_code = main(argv)
print("exit code:", exit_code)
if exit_code == 1:
    raise RuntimeError("eval gate FAILED; see /tmp/abx-reports/latest.md and the MLflow run")
if exit_code:
    raise RuntimeError(f"abx {command} failed with exit code {exit_code}")

# COMMAND ----------

# MAGIC %md
# MAGIC The report is mirrored to `/Volumes/<catalog>/<schema>/ka_data/reports/latest.md`.
