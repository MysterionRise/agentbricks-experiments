# ADR 0004: What we are locked into, and the exit path

Status: accepted. Date: 2026-10-20.

## Context

Choosing a managed agent on one platform invites the question "what if we
leave?" The honest answer is itemised, so a decision maker can weigh it rather
than fear it.

## What moves with us

| Asset | Portability | Notes |
|---|---|---|
| Corpus (`data/corpus/`) | Full | Plain markdown in git. |
| Eval seed (`evals/seed.jsonl`) | Full | Plain JSON lines; the expected facts and guidelines are the valuable part. |
| Gate logic (`src/abx/gate.py`) | Full | Pure Python over a DataFrame; works on any MLflow 3 evaluation output. |
| Judges | High | MLflow's built-in scorers run outside Databricks with any supported judge model. Scores will differ by judge model, so thresholds would be re-baselined. |
| Evaluation dataset in Unity Catalog | Medium | Exportable to a table or JSONL; the versioning and lineage are Databricks features. |
| Report and ADRs | Full | Markdown. |

## What does not move

| Asset | Replacement cost |
|---|---|
| The Knowledge Assistant itself | Rebuild as a retriever + LLM agent (Agent Framework, LangGraph, or a cloud vendor's equivalent). With the corpus and eval in hand, a competent engineer reaches a gated baseline in about a week. |
| Serving endpoint and AI Gateway configuration | Re-create on the target platform's serving layer. |
| System-table cost queries | Re-write against the target's billing export. |
| Asset Bundle jobs | Re-express as the target's scheduler. The CLI underneath is unchanged. |

## Decision

Accept the lock-in for the agent and the serving layer. Keep everything that
defines "correct" and "acceptable" in portable form in the repository. Treat the
eval seed as the most valuable artefact in the project and review changes to it
as carefully as production code.

## Exit trigger

Reconsider when any of these holds for two consecutive quarterly reviews:

- The gate cannot be kept green and the levers available (corpus, instructions,
  examples) are exhausted.
- Cost per 1,000 requests from `reports/latest.md` exceeds the fully loaded
  cost of a self-run alternative by a margin the CFO cares about.
- A required capability (tool use, custom retrieval) is not available and not
  on a published roadmap.
