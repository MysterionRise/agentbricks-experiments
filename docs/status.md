# Product status and change log

What this repository relies on, with the date it was last confirmed. Agent
Bricks moves quickly; a stale row here is a bug.

## Capability matrix

| Capability | Status | Confirmed | Used by |
|---|---|---|---|
| Knowledge Assistant | GA (announced 2026-01-27) | 2026-10-20 | `abx deploy` |
| Knowledge Assistant files source from a UC volume | GA | 2026-10-20 | `abx deploy` |
| `databricks-sdk` `knowledge_assistants` API | available in 0.154.0 | 2026-10-20 | `src/abx/ka.py` |
| Supervisor Agent (formerly Multi-Agent Supervisor) | GA (announced 2026-02-10) | 2026-10-20 | phase 2 |
| `databricks-sdk` `supervisor_agents` API | available in 0.154.0 | 2026-10-20 | phase 2 |
| Information Extraction | Beta per docs | 2026-10-20 | not used |
| Custom LLM (`w.agent_bricks.create_custom_llm`) | in SDK; product status unverified | 2026-10-20 | not used |
| `mlflow.genai.evaluate` with built-in judges | MLflow 3.17 | 2026-10-20 | `abx eval` |
| `mlflow.genai.datasets` in Unity Catalog | MLflow 3.17 | 2026-10-20 | `abx eval` |
| `system.serving.endpoint_usage` | documented system table | not yet run | `abx cost` |
| `system.billing.usage` + `list_prices` | documented system tables | not yet run | `abx cost` |
| Databricks CLI `knowledge-assistants` command group | documented | 2026-10-20 | alternative to SDK |

## Assumptions to confirm on the first real run

1. The Knowledge Assistant endpoint accepts a Responses-style `{"input": [...]}`
   payload. If Playground → Get code shows `messages`, set
   `ABX_REQUEST_SHAPE=chat`.
2. `RetrievalGroundedness` finds retriever spans in the endpoint's traces. If the
   column is empty in the MLflow run, the metric stays reported-only.
3. The cost SQL column names match the workspace's system tables. The report
   says "unavailable" with the SQL error if not.

## Change log

### 2026-10-20

- Rebuilt the repository from a five-notebook UI walkthrough into the `abx`
  package, Asset Bundle, eval gate, cost report and decision records.
- Replaced three unrelated public-domain snippets with a 13-document fictional
  handbook so evaluation answers cannot come from model memory.
- Dropped the Custom LLM example; out of phase 1 scope.
