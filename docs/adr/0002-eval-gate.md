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

## Amendment, 2026-11-04 (before any run)

Written before the first workspace run, so no result informed it. A review of
the Phase 1 code against MLflow 3.17 found that the gate as built could not
produce an honest verdict. The decision above stands; these details change:

- **Rows are matched by seed id.** MLflow's result table has no `inputs`
  column. Each dataset record's tags (`seed_id`, `kind`) are copied onto its
  trace, and the gate reads them from there.
- **Each judge runs only where it applies, in one run.** Built-in judges raise
  on rows without the expectation they need. Correctness and relevance are
  wrapped to skip rows without `expected_facts`, the refusal judge to skip rows
  without `guidelines`. Safety runs on every row. One run keeps one run id and
  the link to the Unity Catalog dataset.
- **Relevance is scoped to answerable rows.** A correct refusal ("the handbook
  does not cover this") is not relevant to the question it declines, so judging
  it would push relevance under 0.85 even for a perfect assistant. The 0.85
  threshold is unchanged; its denominator is now the 31 answerable rows.
- **A missing verdict is a failure.** A judge error, timeout or absent column on
  a row the judge applies to counts against that judge's rate and is reported
  per judge. A row without a safety verdict fails the gate on its own. Only
  retrieval groundedness, which is reported and not gated, skips missing values.
- **Coverage is checked by id.** Every seed id must come back in the results; a
  missing, unmatched or errored row fails the gate. `min_rows_evaluated` stays
  as a second guard.
- **MLflow is pinned to 3.17.x.** `tests/contract` runs a real local
  `mlflow.genai.evaluate` and asserts the columns the gate reads; upgrading MLflow
  means re-running that contract first.

## What this does not do

It does not measure latency, cost, or user satisfaction. Cost is ADR 0003.
Human feedback is phase 3.
