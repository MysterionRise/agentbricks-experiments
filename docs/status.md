# Product status and change log

What this repository relies on, with the date it was last confirmed. Agent
Bricks moves quickly; a stale row here is a bug.

## Capability matrix

| Capability | Status | Confirmed | Used by |
|---|---|---|---|
| Knowledge Assistant | **Legacy** since 2026-10-12 (was GA); keep existing, don't build new | 2026-11-04 | `abx deploy` (Phase 1 baseline) |
| Knowledge Assistant files source from a UC volume | works for existing assistants | 2026-11-04 | `abx deploy` |
| `databricks-sdk` `knowledge_assistants` API | available in 0.154.0 | 2026-11-04 | `src/abx/ka.py` |
| Supervisor Agent (formerly Multi-Agent Supervisor) | **Legacy** since 2026-10-12; Supervisor API end of life 2026-09-30 | 2026-11-04 | not used |
| `databricks-sdk` `supervisor_agents` API | available in 0.154.0 | 2026-11-04 | not used |
| Genie Agents (formerly Genie Spaces), `w.genie` | GA; recommended for new low-code agents | 2026-11-04 | phase 2 |
| Agent Bricks CLI (`databricks-agentbricks`, `agent.toml`) | Beta; recommended for new code agents | 2026-11-04 | phase 2 |
| AI Search (formerly Vector Search) | renamed 2026-06 | 2026-11-04 | phase 2 |
| Declarative Automation Bundles (formerly Asset Bundles) | renamed 2026-03; Databricks CLI v1.23.0 | 2026-11-04 | `databricks.yml` |
| AI Gateway on agent endpoints | inference tables only; no rate limits or usage tracking | 2026-11-04 | ADR 0003 |
| Information Extraction | Beta per docs | 2026-10-20 | not used |
| Custom LLM (`w.agent_bricks.create_custom_llm`) | in SDK; product status unverified | 2026-10-20 | not used |
| `mlflow.genai.evaluate` with built-in judges | MLflow 3.17 pinned; 3.18 released | 2026-11-04 | `abx eval` |
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
4. After a sync, a knowledge source's `knowledge_cutoff_time` moves past the
   newest file in the volume once indexing has finished. `abx deploy` waits for
   that before returning. If deploys time out with sources already `UPDATED`, set
   `ABX_DEPLOY_REQUIRE_FRESH_INDEX=false` and record what the field holds.

## Change log

### 2026-11-04

- Knowledge Assistant and Supervisor Agent are legacy since 2026-10-12. Phase 2
  becomes a migration to the Agent Bricks CLI, measured by the same gate. README,
  CTO brief and ADRs 0001 and 0003 amended.
- Found that no workspace run had ever happened and that the gate could not have
  passed one: it read an `inputs` column MLflow 3.17 does not produce. Fixes are
  tracked in milestone "M0 Phase 1.1: make the gate real".

### 2026-10-20

- Rebuilt the repository from a five-notebook UI walkthrough into the `abx`
  package, Asset Bundle, eval gate, cost report and decision records.
- Replaced three unrelated public-domain snippets with a 13-document fictional
  handbook so evaluation answers cannot come from model memory.
- Dropped the Custom LLM example; out of phase 1 scope.
