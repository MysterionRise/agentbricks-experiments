# Runbook

For whoever is holding the pager. Commands assume the Databricks CLI is
authenticated and `pip install -e .` has been run.

## Objects and owners

| Object | Name (defaults) | Owner |
|---|---|---|
| Schema | `main.ab_demo` | platform engineer running the bundle |
| Volume | `main.ab_demo.ka_data` (`knowledge/`, `reports/`) | same |
| Knowledge Assistant | display name `halcyon-handbook-ka` | same |
| Serving endpoint | read from the assistant; `abx deploy` logs it | Databricks managed |
| Eval dataset | `main.ab_demo.handbook_eval` | same |
| MLflow experiment | `/Shared/abx/handbook-ka` | same |

Override any of these with `ABX_*` variables or `abx --set ABX_KEY=VALUE`.

## Deploy from scratch

```bash
abx validate
abx setup        # schema, volume, 13 files under knowledge/
abx deploy       # creates or reuses the assistant, attaches the files source,
                 # syncs, polls until ACTIVE (up to 30 min on first build)
abx eval         # dataset upsert, judges, gate; exit 1 on failure
abx cost         # needs ABX_SQL_WAREHOUSE_ID
```

`abx deploy` is idempotent: it finds the assistant by display name and the
source by volume path. Running it after a corpus change re-syncs the source.

## Update the corpus

1. Edit or add markdown under `data/corpus/`.
2. If the change makes a seed answer wrong, update `evals/seed.jsonl` in the same
   pull request. `pytest` checks every `source_docs` entry exists.
3. `abx setup` to upload, `abx deploy` to re-sync, `abx eval` to prove it.

## Confirm the endpoint payload shape

Open the assistant in AI Playground, click **Get code**. If the snippet posts
`{"input": [...]}` the default is right. If it posts `{"messages": [...]}` set
`ABX_REQUEST_SHAPE=chat`. The eval dataset stores inputs in that shape, so
changing it changes the dataset's rows (a new version is created; nothing is
lost).

## The gate failed

1. Open the MLflow run named in `reports/latest.md`. The three worst rows and the
   judge's rationale are in the report; every row is in the run.
2. Sort failures by kind:
   - `out_of_scope` failures: the instructions are too permissive. Tighten
     `ABX_KA_INSTRUCTIONS` and redeploy; the assistant's instructions are updated
     only on creation in phase 1, so delete and recreate, or edit in the UI.
   - `multi_doc` failures with `direct` passing: retrieval returns one document.
     Shorten documents or add a cross-reference line to each affected document.
   - Widespread `correctness` failures after no change on our side: the vendor
     changed something. Compare with the previous run; raise with Databricks
     support with both run ids.
3. Never lower a threshold to go green. If the threshold is wrong, change it in
   `pyproject.toml` with a sentence in the PR explaining why.

## Roll back

The assistant has no versions. Rollback means restoring the previous corpus:

```bash
git checkout <previous-sha> -- data/corpus
abx setup && abx deploy && abx eval
```

Switch consumers to a previous endpoint only if you deployed a second assistant
under a different `ABX_KA_DISPLAY_NAME`, which is the blue/green pattern for a
risky corpus change.

## Rotate credentials

The GitHub workflow uses `DATABRICKS_HOST` and `DATABRICKS_TOKEN` repository
secrets. Create the token for a service principal, not a person. Rotate by
generating a new token, updating the secret, and revoking the old one. Nothing
in the repo or the report carries the host or the token.

## Remove everything

```bash
databricks bundle destroy -t dev
databricks knowledge-assistants delete-knowledge-assistant <name>
```

Then drop the schema. The eval dataset and experiment go with it.

## At 3 a.m.

The assistant is read-only over policy documents. If it is down, the right
action is to say so and point people at the handbook in Atlas; nothing in this
project needs an emergency fix outside working hours.
