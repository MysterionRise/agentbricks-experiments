"""MLflow glue: the UC evaluation dataset, the scorers, and one evaluation run.

``run_evaluation`` is the workspace entry point. ``ensure_dataset`` and
``evaluate_dataset`` hold the MLflow logic and also run offline against a local
MLflow store, which is how ``tests/contract`` exercises them. The pure parts
(seed validation, the gate) are in ``seed.py`` and ``gate.py``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import mlflow
from mlflow.genai.datasets import create_dataset, get_dataset
from mlflow.genai.scorers import (
    Correctness,
    ExpectationsGuidelines,
    RelevanceToQuery,
    RetrievalGroundedness,
    Safety,
    Scorer,
    scorer,
)

from abx.gate import (
    CORRECTNESS,
    GROUNDEDNESS,
    GUIDELINES,
    RELEVANCE,
    SAFETY,
    EvalSummary,
    summarize,
)
from abx.seed import SeedRecord, seed_hash, to_mlflow_records

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from mlflow.genai.datasets import EvaluationDataset

    from abx.config import Settings
    from abx.seed import RequestShape

log = logging.getLogger(__name__)


def configure_tracking(settings: Settings) -> str:
    """Point MLflow at the workspace and at the project's experiment."""
    mlflow.set_tracking_uri("databricks")
    mlflow.set_registry_uri("databricks-uc")
    experiment = mlflow.set_experiment(settings.experiment_path)
    return str(experiment.experiment_id)


class DatasetMismatchError(RuntimeError):
    """The evaluation dataset does not hold exactly the seed's rows."""


ExistsFn = Callable[[str], bool]


def dataset_name(settings: Settings, records: list[SeedRecord]) -> str:
    """One dataset per seed version: ``<catalog>.<schema>.<eval_dataset>_<hash>``.

    MLflow datasets are upsert-only, so editing or removing a seed question would
    leave a stale row behind in a single long-lived dataset. Naming the dataset
    after the seed content makes each version immutable; the old one stays for
    lineage of earlier runs.
    """
    return f"{settings.eval_dataset_fqn}_{seed_hash(records, settings.request_shape)}"


def ensure_dataset(
    name: str,
    records: list[SeedRecord],
    request_shape: RequestShape,
    experiment_id: str,
    exists: ExistsFn,
) -> EvaluationDataset:
    """Get or create the dataset, merge the seed, and check it matches exactly.

    Merging on every run is idempotent and repairs a dataset whose first write
    was interrupted. ``exists`` is injected because how a missing dataset
    surfaces differs between a workspace (a Unity Catalog table) and a local store.
    """
    dataset: EvaluationDataset
    if exists(name):
        log.info("dataset exists: %s", name)
        dataset = get_dataset(name=name)
    else:
        log.info("creating dataset %s", name)
        dataset = create_dataset(name=name, experiment_id=experiment_id)
    # On Databricks merge_records returns a new wrapper; locally it returns self.
    merged: EvaluationDataset | None = dataset.merge_records(
        to_mlflow_records(records, request_shape)
    )
    if merged is not None:
        dataset = merged
    count = len(dataset.to_df())
    if count != len(records):
        msg = f"dataset {name} has {count} rows, the seed has {len(records)}"
        raise DatasetMismatchError(msg)
    return dataset


def scoped(inner: Scorer, needs: str) -> Scorer:
    """Run ``inner`` only on rows whose expectations carry ``needs``.

    Built-in judges raise on rows they do not apply to (Correctness without
    ``expected_facts``, ExpectationsGuidelines without ``guidelines``), which logs
    a judge error on every such row. Returning None instead records no verdict
    for that row, and the gate scopes each judge to the kinds it applies to. The
    wrapper keeps the inner judge's name, so its column is unchanged. The
    Databricks harness passes expectations under the same keys.
    """

    def judge(
        inputs: dict[str, Any] | None,
        outputs: object,
        expectations: dict[str, Any] | None,
        trace: object,
    ) -> object:
        if not (expectations or {}).get(needs):
            return None
        # Scorer.run filters these to the inner judge's own signature.
        return inner.run(  # type: ignore[no-untyped-call]
            inputs=inputs, outputs=outputs, expectations=expectations, trace=trace
        )

    return scorer(judge, name=inner.name)


def default_judges() -> dict[str, Scorer]:
    """MLflow's built-in judges, keyed by the result column each one writes."""
    return {
        CORRECTNESS: Correctness(),
        RELEVANCE: RelevanceToQuery(),
        GUIDELINES: ExpectationsGuidelines(),
        SAFETY: Safety(),  # type: ignore[no-untyped-call]
        GROUNDEDNESS: RetrievalGroundedness(),
    }


def build_scorers(judges: Mapping[str, Scorer] | None = None) -> list[Scorer]:
    """The judge set, each scoped to the rows it applies to.

    ``judges`` replaces the built-in judges, keyed like :func:`default_judges`;
    the contract test passes deterministic ones.
    """
    j = dict(judges) if judges is not None else default_judges()
    return [
        scoped(j[CORRECTNESS], "expected_facts"),
        scoped(j[RELEVANCE], "expected_facts"),
        scoped(j[GUIDELINES], "guidelines"),
        j[SAFETY],
        j[GROUNDEDNESS],
    ]


def evaluate_dataset(
    dataset: EvaluationDataset,
    name: str,
    records: list[SeedRecord],
    predict_fn: Callable[..., Any],
    scorers: list[Scorer],
    run_name: str,
    tags: Mapping[str, str],
) -> EvalSummary:
    """Run one MLflow evaluation of ``dataset`` and summarise it for the gate."""
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.set_tags({**tags, "abx.dataset": name})
        result = mlflow.genai.evaluate(data=dataset, predict_fn=predict_fn, scorers=scorers)
        run_id = str(getattr(result, "run_id", None) or run.info.run_id)

    result_df = getattr(result, "result_df", None)
    if result_df is None:
        msg = "mlflow.genai.evaluate returned no result_df; cannot gate"
        raise RuntimeError(msg)
    return summarize(run_id, result_df, records, dataset_fqn=name)


def run_evaluation(
    settings: Settings,
    endpoint_name: str,
    records: list[SeedRecord],
    seed_path: Path | None = None,
    exists: ExistsFn | None = None,
) -> EvalSummary:
    """Evaluate the endpoint against this seed version's dataset in the workspace."""
    if exists is None:
        from databricks.sdk import WorkspaceClient

        tables = WorkspaceClient().tables

        def exists(full_name: str) -> bool:
            return bool(tables.exists(full_name).table_exists)

    experiment_id = configure_tracking(settings)
    name = dataset_name(settings, records)
    dataset = ensure_dataset(name, records, settings.request_shape, experiment_id, exists)
    return evaluate_dataset(
        dataset,
        name,
        records,
        predict_fn=mlflow.genai.to_predict_fn(f"endpoints:/{endpoint_name}"),
        scorers=build_scorers(),
        run_name=f"eval-{endpoint_name}",
        tags={
            "abx.endpoint": endpoint_name,
            "abx.seed": str(seed_path) if seed_path else "evals/seed.jsonl",
        },
    )
