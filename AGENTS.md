# Repository Guidelines

## Structure

Python 3.12 package `abx` in `src/abx/`. `cli.py` is the entry point with the
subcommands `validate`, `setup`, `deploy`, `eval`, `cost`. `config.py` holds
`Settings` (pydantic-settings, `ABX_` prefix). `corpus.py` and `ka.py` talk to
the Databricks SDK; `evaluate.py` talks to MLflow; `seed.py`, `gate.py`,
`cost.py` (apart from one SQL call) and `report.py` are pure and fully
unit-tested. Content lives in `data/corpus/` and `evals/seed.jsonl`. Infra is
`databricks.yml` + `resources/jobs.yml` and `.github/workflows/`. Decisions are
in `docs/adr/`.

## Commands

- `pip install -e ".[dev]"`: install the package and tooling.
- `abx validate`: offline check of seed, corpus and thresholds.
- `pytest`: unit tests with coverage (minimum 70%). No test needs a workspace.
- `ruff check src/ tests/` and `ruff format --check src/ tests/`.
- `mypy src/`: strict.
- `pre-commit run --all-files`: the full local gate; CI runs the same hooks.
- `databricks bundle validate -t dev`: bundle schema check.

## Style

Ruff formatting, 100-character lines, double quotes, sorted imports with `abx`
first-party. Production code fully typed. Modules that touch a workspace keep
the SDK call thin so tests can mock `WorkspaceClient` with `MagicMock`.
Logging, never `print`, in `src/`.

## Testing

Tests under `tests/unit/`, named `test_*.py`. Mock the SDK and MLflow; never
reach the network. Tests that read `evals/seed.jsonl` or `data/corpus/` are the
schema check for content changes: update both when a policy fact changes.

## Content rules

- The corpus is fictional on purpose (see `docs/adr/0002-eval-gate.md`). Do not
  add real companies, people, or public-domain texts a model may already know.
- The seed is a held-out test set. Never push it to the assistant as examples.
- Thresholds change only in `pyproject.toml` `[tool.abx.gate]`, with a reason in
  the PR.
- `reports/latest.md` is generated. Do not hand-edit it, and never put numbers
  in it that did not come from a run.

## Commits and PRs

Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `ci:`), checked by
Commitizen in pre-commit. PRs state whether `abx eval` was run on a workspace
and link the MLflow run when it was. No workspace hosts, tokens, or user names in
any committed file.
