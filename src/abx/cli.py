"""``abx`` command line: setup, deploy, eval, cost.

Each subcommand is one job task in the Asset Bundle and one step in the README.
Exit code 1 means the eval gate failed; 2 means a deploy or query error.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from abx.config import Settings

log = logging.getLogger("abx")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = REPO_ROOT / "data" / "corpus"
DEFAULT_SEED = REPO_ROOT / "evals" / "seed.jsonl"
DEFAULT_PYPROJECT = REPO_ROOT / "pyproject.toml"
DEFAULT_OUT = REPO_ROOT / "reports"


def build_parser() -> argparse.ArgumentParser:
    """Argument parser; kept separate so tests can exercise it."""
    parser = argparse.ArgumentParser(prog="abx", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="ABX_KEY=VALUE",
        help="override a setting for this run; the Asset Bundle passes variables this way",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_setup = sub.add_parser("setup", help="create schema and volume, upload the corpus")
    p_setup.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)

    sub.add_parser("deploy", help="create or reuse the Knowledge Assistant and wait for ACTIVE")

    p_eval = sub.add_parser("eval", help="run the MLflow evaluation and apply the gate")
    p_eval.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    p_eval.add_argument("--pyproject", type=Path, default=DEFAULT_PYPROJECT)
    p_eval.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p_eval.add_argument("--no-volume", action="store_true", help="skip mirroring to the volume")

    p_cost = sub.add_parser("cost", help="query system tables and refresh the report")
    p_cost.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p_cost.add_argument("--no-volume", action="store_true")

    p_validate = sub.add_parser("validate", help="validate the seed and corpus offline")
    p_validate.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    p_validate.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    p_validate.add_argument("--pyproject", type=Path, default=DEFAULT_PYPROJECT)

    return parser


def cmd_validate(args: argparse.Namespace) -> int:
    """Offline checks: seed schema, corpus present, thresholds parse."""
    from abx.corpus import load_corpus
    from abx.gate import GateThresholds
    from abx.seed import load_seed

    records = load_seed(args.seed)
    docs = load_corpus(args.corpus)
    thresholds = GateThresholds.from_pyproject(args.pyproject)
    kinds = {
        k: sum(1 for r in records if r.kind == k) for k in ("direct", "multi_doc", "out_of_scope")
    }
    log.info("seed ok: %d rows %s", len(records), kinds)
    log.info("corpus ok: %d documents", len(docs))
    log.info("gate ok: %s", thresholds.model_dump())
    if len(records) < thresholds.min_rows_evaluated:
        log.error("seed has fewer rows than min_rows_evaluated")
        return 2
    return 0


def cmd_setup(args: argparse.Namespace, settings: Settings) -> int:
    """Create UC objects and upload the corpus."""
    from databricks.sdk import WorkspaceClient

    from abx.corpus import ensure_schema_and_volume, load_corpus, upload_corpus

    w = WorkspaceClient()
    ensure_schema_and_volume(w, settings)
    uploaded = upload_corpus(w, settings, load_corpus(args.corpus))
    log.info("knowledge folder ready: %s (%d files)", settings.knowledge_path, len(uploaded))
    return 0


def cmd_deploy(settings: Settings) -> int:
    """Create or reuse the assistant and wait until it serves."""
    from databricks.sdk import WorkspaceClient

    from abx.ka import DeployError, deploy

    w = WorkspaceClient()
    try:
        assistant = deploy(w, settings)
    except DeployError as exc:
        log.error("%s", exc)
        return 2
    log.info("assistant ACTIVE: endpoint=%s", assistant.endpoint_name)
    return 0


def cmd_eval(args: argparse.Namespace, settings: Settings) -> int:
    """Evaluate, gate, and write the report. Exit 1 when the gate fails."""
    from databricks.sdk import WorkspaceClient

    from abx.evaluate import run_evaluation
    from abx.gate import GateThresholds, apply_gate
    from abx.ka import DeployError, resolve_endpoint_name
    from abx.report import render_report, write_local, write_volume
    from abx.seed import load_seed

    records = load_seed(args.seed)
    thresholds = GateThresholds.from_pyproject(args.pyproject)
    w = WorkspaceClient()
    try:
        endpoint = resolve_endpoint_name(w, settings)
    except DeployError as exc:
        log.error("%s", exc)
        return 2

    summary = run_evaluation(settings, endpoint, records, seed_path=args.seed)
    verdict = apply_gate(summary, thresholds)
    report = render_report(summary, verdict, None, endpoint, settings.eval_dataset_fqn)
    path = write_local(args.out, report, summary)
    if not args.no_volume:
        write_volume(w, settings.reports_path, report, summary)
    log.info("report written: %s", path)
    for reason in verdict.reasons:
        log.error("gate: %s", reason)
    log.info("gate %s", "PASSED" if verdict.passed else "FAILED")
    return 0 if verdict.passed else 1


def cmd_cost(args: argparse.Namespace, settings: Settings) -> int:
    """Refresh the cost section, keeping the last eval section if one exists."""
    from databricks.sdk import WorkspaceClient

    from abx.cost import fetch_cost
    from abx.gate import GateThresholds, apply_gate
    from abx.ka import DeployError, resolve_endpoint_name
    from abx.report import read_summary, render_report, write_local, write_volume

    w = WorkspaceClient()
    try:
        endpoint = resolve_endpoint_name(w, settings)
    except DeployError as exc:
        log.error("%s", exc)
        return 2
    cost = fetch_cost(w, settings, endpoint)
    summary = read_summary(args.out)
    verdict = None
    if summary is not None:
        verdict = apply_gate(summary, GateThresholds.from_pyproject(DEFAULT_PYPROJECT))
    report = render_report(summary, verdict, cost, endpoint, settings.eval_dataset_fqn)
    path = write_local(args.out, report, summary)
    if not args.no_volume:
        write_volume(w, settings.reports_path, report, summary)
    log.info("report written: %s (cost available=%s)", path, cost.available)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.command == "validate":
        return cmd_validate(args)
    for item in args.set:
        key, sep, value = item.partition("=")
        if not sep or not key.startswith("ABX_"):
            log.error("--set expects ABX_KEY=VALUE, got %r", item)
            return 2
        os.environ[key] = value
    settings = Settings()
    if args.command == "setup":
        return cmd_setup(args, settings)
    if args.command == "deploy":
        return cmd_deploy(settings)
    if args.command == "eval":
        return cmd_eval(args, settings)
    if args.command == "cost":
        return cmd_cost(args, settings)
    return 2


if __name__ == "__main__":
    sys.exit(main())
