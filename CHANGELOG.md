# Changelog

All notable changes to this project are documented here. The format follows
Keep a Changelog; versions follow Semantic Versioning.

## [Unreleased]

### Added

- `abx` package with `validate`, `setup`, `deploy`, `eval`, `cost` commands.
- Idempotent Knowledge Assistant deployment through the Databricks SDK.
- Evaluation gate: UC-backed MLflow dataset, five built-in judges, thresholds in
  `pyproject.toml`, non-zero exit on failure.
- Cost report from `system.serving` and `system.billing` tables.
- Asset Bundle with four serverless jobs; `Eval gate` GitHub workflow.
- Fictional 13-document handbook corpus and a 39-question seed.
- ADRs 0001–0004, CTO brief, status matrix, runbook.
- Quality gate: ruff, strict mypy, bandit, gitleaks, pytest with coverage, CI.

### Removed

- The five UI-first demo notebooks and the Custom LLM example. A single
  `notebooks/run_abx.py` wraps the CLI instead.

## [0.1.0] - 2025-10-05

- Initial five-notebook Agent Bricks demo.
