# Agent Bricks on Databricks — Minimal Demo

This repo gives you a tiny, data-safe starter to try two Agent Bricks use cases on your own Databricks workspace:

1. **Knowledge Assistant** over UC Volume files (public-domain docs written by a notebook).
2. **Custom LLM** using a toy labeled table.

> **Note:** Agent Bricks is in Beta and features/regions may vary. Ensure your workspace meets the requirements (Unity Catalog, Serverless compute, access to foundation models via `system.ai`, serverless budget policy, and—specifically for Knowledge Assistant—files in a UC Volume or a Vector Search index that uses `databricks-gte-large-en`). See official docs.

**AWS docs:** https://docs.databricks.com/aws/en/generative-ai/agent-bricks/
**Knowledge Assistant:** https://docs.databricks.com/aws/en/generative-ai/agent-bricks/knowledge-assistant
**Multi‑Agent Supervisor** (optional, later): https://docs.databricks.com/aws/en/generative-ai/agent-bricks/multi-agent-supervisor

## What's inside

- `notebooks/00_check_prereqs.py` – prints context and checks for embedding endpoint `databricks-gte-large-en`.
- `notebooks/01_setup_catalog_schema_volume.py` – creates `catalog.schema.volume` (defaults: `main.ab_demo.ka_data`).
- `notebooks/02_load_sample_docs_to_volume.py` – writes 3 markdown files into `/Volumes/<catalog>/<schema>/<volume>/knowledge`.
- `notebooks/03_build_custom_llm_dataset.py` – creates `main.ab_demo.custom_llm_tiny` with `(request,response)` examples.
- `notebooks/04_query_knowledge_assistant_example.py` – template to query your KA endpoint using MLflow Deployments.

## Quickstart (UI-first)

1. Import or clone this repo into **Databricks Repos**.
2. Open and run:
   - `00_check_prereqs.py`
   - `01_setup_catalog_schema_volume.py` (adjust widgets if you can't create in `main`)
   - `02_load_sample_docs_to_volume.py`
3. In the left nav, go to **Agents → Knowledge Assistant** and click **Create**.
4. Add a **Knowledge source** of type **UC Files**.
   - **Source:** the volume path printed by notebook 01 (ends with `/knowledge` from notebook 02).
5. Finish creation. Initial build/sync can take time; you'll get a deployed endpoint when ready.
6. Test in **AI Playground**. Click **Get code** there to copy the official Python snippet for querying the endpoint.
7. (Optional) Open `04_query_knowledge_assistant_example.py`, set `ENDPOINT_NAME`, and run to test via MLflow Deployments.

## Optional: Custom LLM demo

1. Run `03_build_custom_llm_dataset.py` to create `main.ab_demo.custom_llm_tiny`.
2. In **Agents → Custom LLM**, create a new agent:
   - **Instructions:** e.g., _"Classify a support ticket into Billing, Shipping, or Tech."_
   - **Datasets:** point to the created table, `request` as request column, `response` as response column.
3. Let Agent Bricks optimize/evaluate and deploy the endpoint.
4. Use Playground's **Get code** to query the Custom LLM endpoint from notebooks or apps.

## Local dev or Jobs (optional)

- `requirements.txt` lists the few libs you might pip‑install locally.
- For CI/CD or Jobs via Asset Bundles, see Databricks docs on [Databricks Asset Bundles (DABs)](https://docs.databricks.com/en/dev-tools/bundles/index.html) and adjust as needed.

## Notes

- We only use public-domain snippets for sample docs.
- If your workspace lacks permission to create catalogs/schemas/volumes in `main`, change the widgets in notebook 01.
- Knowledge Assistant does not take UC tables as direct input (use files in volumes or a supported Vector Search index).
