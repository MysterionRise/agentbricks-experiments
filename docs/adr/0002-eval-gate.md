# ADR 0002: An evaluation gate blocks the deploy

Status: accepted. Date: 2026-10-20.

## Context

A managed agent can be reconfigured, re-synced, or silently upgraded by the
vendor. Without a repeatable measurement we would learn about regressions from
users. The gate turns "is it good?" into a number computed the same way every
time, with a threshold that is reviewed in a pull request.

## Decision

1. **A held-out seed in the repo.** `evals/seed.jsonl` is hand-written, versioned,
   and validated by a unit test. It is never pushed to the assistant as examples.
   Training on the test set would make the number meaningless.
2. **A fictional corpus.** The handbook describes a company that does not exist.
   A judge or the assistant cannot answer from pre-training, so a correct answer
   is evidence of retrieval. Public-domain documents were considered and rejected
   for this reason: models already know them.
3. **Three kinds of question.** `direct` (one document), `multi_doc` (two documents,
   sometimes arithmetic), `out_of_scope` (the handbook is silent). The third kind
   is the one stakeholders ask about first: does it make things up?
4. **MLflow's built-in judges**, not hand-rolled prompts. `Correctness`
   checks expected facts are supported; `ExpectationsGuidelines` checks the
   per-row refusal rule; `RelevanceToQuery`, `Safety`, and
   `RetrievalGroundedness` round it out. The dataset lives in Unity Catalog via
   `mlflow.genai.datasets`, so it is versioned and has lineage to each run.
5. **Thresholds in `pyproject.toml`.** `[tool.abx.gate]` is read at run time.
   Lowering a threshold is a diff with a reviewer, not a flag on a job.
6. **Fail closed.** A missing judge output (no column, all NaN) fails the gate.
   An empty or truncated dataset fails the gate (`min_rows_evaluated`).

## Thresholds and why

| Threshold | Value | Reason |
|---|---|---|
| Correctness mean | 0.80 | Below this, one in five answers is missing a fact. Users stop trusting it. |
| Relevance mean | 0.85 | Catches the assistant wandering off-topic, independent of facts. |
| Out-of-scope refusal | 0.90 | Fabrication is the failure mode that ends pilots. One slip in ten is the ceiling. |
| Safety failures | 0 | Non-negotiable for an employee-facing tool. |
| Min rows | 30 | Fewer rows and a single judge flip moves the mean by more than 3 points. |

Retrieval groundedness is reported but not gated in phase 1: the Knowledge
Assistant's traces may not expose retriever spans in a way the judge reads
consistently. Once a real run shows it is populated, it becomes a gate.

## Consequences

- `abx eval` exits 1 on failure; the Asset Bundle job and the GitHub workflow
  inherit that. A red workflow is the signal, not a dashboard someone must open.
- Every run leaves an MLflow run with per-row assessments and traces for the
  three worst rows, so a failure is debuggable without re-running.
- A weekly scheduled run (paused by default in `resources/jobs.yml`) turns the
  same gate into drift detection.

## What this does not do

It does not measure latency, cost, or user satisfaction. Cost is ADR 0003.
Human feedback is phase 3.
