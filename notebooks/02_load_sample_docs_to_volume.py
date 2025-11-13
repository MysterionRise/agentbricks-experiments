# Databricks notebook source
# MAGIC %md
# MAGIC # Write public‑domain sample docs into the UC Volume
# MAGIC
# MAGIC Knowledge Assistant (KA) can ingest UC Files from a volume.
# MAGIC We'll create a few small markdown documents under /knowledge.

# COMMAND ----------

dbutils.widgets.text("catalog", "main", "catalog")
dbutils.widgets.text("schema", "ab_demo", "schema")
dbutils.widgets.text("volume", "ka_data", "volume")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
volume = dbutils.widgets.get("volume")

knowledge_dir = f"/Volumes/{catalog}/{schema}/{volume}/knowledge"
dbutils.fs.mkdirs(knowledge_dir)

# Public‑domain / US Gov sources summarized or excerpted in our own words
constitution_md = """# U.S. Constitution (excerpt, public domain)

## Preamble

We the People of the United States, in Order to form a more perfect Union, 
establish Justice, insure domestic Tranquility, provide for the common defence, 
promote the general Welfare, and secure the Blessings of Liberty to ourselves 
and our Posterity, do ordain and establish this Constitution for the United 
States of America.

## Article I (selected)

The legislative powers are vested in a Congress of the United States.

Congress has enumerated powers such as taxation, regulating commerce, and 
declaring war.
"""

nasa_md = """# NASA Mars Notes (public domain)

Perseverance rover landed in Jezero Crater in 2021 to seek signs of ancient 
life and collect rock cores for possible return to Earth. The mission includes 
the Ingenuity helicopter technology demonstration. Roving targets include delta 
deposits, crater floor units, and carbonate‑bearing rocks that can preserve 
biosignatures.
"""

fema_md = """# FEMA Preparedness Basics (public domain)

Preparedness includes: making a family emergency plan, assembling supplies 
(water, food, medications), staying informed via local alerting systems, and 
rehearsing evacuation routes. For businesses, continuity planning covers 
critical functions, backups, and communication trees.
"""

files = {
    "us_constitution_excerpt.md": constitution_md,
    "nasa_mars_notes.md": nasa_md,
    "fema_preparedness_basics.md": fema_md,
}

for name, content in files.items():
    path = f"{knowledge_dir}/{name}"
    dbutils.fs.put(path, content, overwrite=True)

print("Wrote files to:", knowledge_dir)
display(dbutils.fs.ls(knowledge_dir))

# COMMAND ----------

# MAGIC %md
# MAGIC Next: Create a Knowledge Assistant in the Databricks UI and point its
# MAGIC Knowledge source to this folder.
