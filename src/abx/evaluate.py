"""MLflow glue: the UC evaluation dataset, the scorers, and one evaluation run.

Everything here needs a workspace. The pure parts (seed validation, the gate)
are in ``seed.py`` and ``gate.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import mlflow
from mlflow.genai.datasets import create_dataset, get_dataset
from mlflow.genai.scorers import (
    Correctness,
    ExpectationsGuidelines,
    RelevanceToQuery,
    RetrievalGroundedness,
    Safety,
)

from abx.gate import EvalSummary, summarize
from abx.seed import SeedRecord, kinds_by_question, to_mlflow_records

if TYPE_CHECKING:
    from pathlib import Path

    from mlflow.genai.datasets import EvaluationDataset

    from abx.config import Settings

log = logging.getLogger(__name__)


def configure_tracking(settings: Settings) -> str:
    """Point MLflow at the workspace and at the project's experiment."""
    mlflow.set_tracking_uri("databricks")
    mlflow.set_registry_uri("databricks-uc")
    experiment = mlflow.set_experiment(settings.experiment_path)
    return str(experiment.experiment_id)


def upsert_dataset(
    settings: Settings, records: list[SeedRecord], experiment_id: str
) -> EvaluationDataset:
    """Create the UC-backed dataset on first use; merge the seed rows on every run.

    ``merge_records`` de-duplicates on inputs, so re-running with an unchanged seed
    is a no-op and a changed seed produces a new dataset version with lineage.
    """
    name = settings.eval_dataset_fqn
    dataset: EvaluationDataset
    try:
        dataset = get_dataset(name=name)
        log.info("dataset exists: %s", name)
    except Exception:
        log.info("creating dataset %s", name)
        dataset = create_dataset(name=name, experiment_id=experiment_id)
    dataset.merge_records(to_mlflow_records(records, settings.request_shape))
    return dataset


def build_scorers() -> list[Any]:
    """The judge set. Each maps to one column the gate reads."""
    return [
        Correctness(),
        RelevanceToQuery(),
        RetrievalGroundedness(),
        ExpectationsGuidelines(),
        Safety(),  # type: ignore[no-untyped-call]
    ]


def run_evaluation(
    settings: Settings,
    endpoint_name: str,
    records: list[SeedRecord],
    seed_path: Path | None = None,
) -> EvalSummary:
    """Evaluate the endpoint against the dataset and summarise per kind."""
    experiment_id = configure_tracking(settings)
    dataset = upsert_dataset(settings, records, experiment_id)
    predict_fn = mlflow.genai.to_predict_fn(f"endpoints:/{endpoint_name}")

    with mlflow.start_run(run_name=f"eval-{endpoint_name}") as run:
        mlflow.set_tags(
            {
                "abx.endpoint": endpoint_name,
                "abx.dataset": settings.eval_dataset_fqn,
                "abx.seed": str(seed_path) if seed_path else "evals/seed.jsonl",
            }
        )
        result = mlflow.genai.evaluate(
            data=dataset,
            predict_fn=predict_fn,
            scorers=build_scorers(),
        )
        run_id = str(getattr(result, "run_id", None) or run.info.run_id)

    result_df = getattr(result, "result_df", None)
    if result_df is None:
        msg = "mlflow.genai.evaluate returned no result_df; cannot gate"
        raise RuntimeError(msg)
    return summarize(run_id, result_df, kinds_by_question(records))
