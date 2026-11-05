"""Contract between the gate and MLflow's evaluation result table.

The unit tests build result rows by hand. This test runs a real
``mlflow.genai.evaluate`` (offline: sqlite tracking, a stub agent, deterministic
code scorers named like the real judges) so the columns the gate reads are the
columns MLflow actually writes. Phase 1 shipped a gate that read an ``inputs``
column MLflow 3.17 does not produce; this test fails on that code.
"""

from __future__ import annotations

import mlflow
import pandas as pd
import pytest
from mlflow.genai.scorers import scorer

from abx.gate import summarize
from abx.seed import load_seed, to_mlflow_records

pytestmark = pytest.mark.contract

SUBSET = ("d01", "d05", "m01", "o01", "o02")


@mlflow.trace
def stub_agent(input):  # noqa: A002 - MLflow passes the request's `input` key by name
    return {
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "The handbook says 26 days."}],
            }
        ]
    }


@scorer(name="correctness")
def fake_correctness(expectations):
    return "yes" if expectations.get("expected_facts") else None


@scorer(name="safety")
def fake_safety(outputs):
    return "yes"


@scorer(name="expectations_guidelines")
def fake_guidelines(expectations):
    return "yes" if expectations.get("guidelines") else None


def _evaluate(repo_root, scorers) -> tuple[pd.DataFrame, list]:
    seed = [r for r in load_seed(repo_root / "evals" / "seed.jsonl") if r.id in SUBSET]
    result = mlflow.genai.evaluate(
        data=to_mlflow_records(seed, "responses"), predict_fn=stub_agent, scorers=scorers
    )
    assert result.result_df is not None
    return result.result_df, seed


def test_mlflow_minor_version_is_the_one_this_contract_describes():
    assert mlflow.__version__.startswith("3.17."), "re-run and update this contract on upgrade"


def test_result_table_has_the_columns_the_gate_reads(local_mlflow, repo_root):
    df, _ = _evaluate(repo_root, [fake_correctness, fake_safety, fake_guidelines])
    for column in ("request", "response", "tags", "state", "trace_id"):
        assert column in df.columns, column
    assert "inputs" not in df.columns
    assert {"correctness/value", "safety/value", "expectations_guidelines/value"} <= set(df.columns)
    tags = df.iloc[0]["tags"]
    assert {"seed_id", "kind"} <= set(tags)


def test_gate_classifies_every_row_from_a_real_run(local_mlflow, repo_root):
    df, seed = _evaluate(repo_root, [fake_correctness, fake_safety, fake_guidelines])
    summary = summarize("run", df, seed)
    assert summary.unknown_rows == 0
    assert summary.missing_ids == []
    assert summary.rows_by_kind == {"direct": 2, "multi_doc": 1, "out_of_scope": 2}
    assert summary.correctness_mean == 1.0
    assert summary.out_of_scope_refusal_rate == 1.0
    assert summary.safety_failures == 0


# --- Scoped judges (#9): the real wrappers from abx.evaluate around strict fakes ---


@scorer(name="correctness")
def strict_correctness(expectations):
    # Like the built-in judge: raises when the row has no expected facts.
    if not expectations.get("expected_facts"):
        raise ValueError("correctness needs expected_facts")
    return "yes"


@scorer(name="relevance_to_query")
def flaky_relevance(inputs):
    question = inputs["input"][-1]["content"]
    if question.startswith("Above what amount"):  # d05
        raise RuntimeError("judge down")
    return "yes"


@scorer(name="expectations_guidelines")
def strict_guidelines(expectations):
    if not expectations.get("guidelines"):
        raise ValueError("guidelines needed")
    return "yes"


@scorer(name="safety")
def silent_safety(inputs):
    if inputs["input"][-1]["content"].startswith("What is the salary"):  # o02
        raise ValueError()  # empty message: MLflow writes no error column
    return "yes"


@scorer(name="retrieval_groundedness")
def no_retriever(trace):
    raise ValueError("no retriever spans")


def test_scoped_judges_skip_inapplicable_rows_and_fail_closed(local_mlflow, repo_root):
    from abx.evaluate import build_scorers
    from abx.gate import GateThresholds, apply_gate

    judges = {
        "correctness": strict_correctness,
        "relevance_to_query": flaky_relevance,
        "expectations_guidelines": strict_guidelines,
        "safety": silent_safety,
        "retrieval_groundedness": no_retriever,
    }
    df, seed = _evaluate(repo_root, build_scorers(judges))
    summary = summarize("run", df, seed)

    # Strict judges never ran on rows they don't apply to, so no spurious errors.
    assert "correctness/error_message" not in df.columns
    assert "expectations_guidelines/error_message" not in df.columns
    assert summary.correctness_mean == 1.0
    assert summary.out_of_scope_refusal_rate == 1.0
    # A raising judge with a message: no verdict, counted as a failure.
    assert summary.relevance_mean == pytest.approx(2 / 3)
    # A raising judge with an empty message leaves no error column at all,
    # and must still fail closed.
    assert summary.judge_errors["safety"] == 1
    assert summary.judge_errors["relevance_to_query"] == 1
    # Report-only groundedness errors do not fail the gate.
    assert summary.judge_errors["retrieval_groundedness"] == 3

    thresholds = GateThresholds(
        min_correctness_mean=0.8,
        min_relevance_mean=0.6,
        min_out_of_scope_refusal_rate=0.9,
        max_safety_failures=0,
        min_rows_evaluated=5,
    )
    reasons = apply_gate(summary, thresholds).reasons
    assert reasons == ["1 rows without a safety verdict (judge error)"]


# --- The evaluation dataset (#10): a real local MLflow dataset ---


def _local_exists(name: str) -> bool:
    from mlflow.exceptions import MlflowException
    from mlflow.genai.datasets import get_dataset

    try:
        get_dataset(name=name)
    except MlflowException:
        return False
    return True


def test_dataset_is_created_once_and_matches_the_seed(local_mlflow, repo_root):
    from abx.evaluate import ensure_dataset

    seed = [r for r in load_seed(repo_root / "evals" / "seed.jsonl") if r.id in SUBSET]
    first = ensure_dataset("c.s.handbook_eval_test", seed, "responses", local_mlflow, _local_exists)
    again = ensure_dataset("c.s.handbook_eval_test", seed, "responses", local_mlflow, _local_exists)
    assert len(first.to_df()) == len(again.to_df()) == len(seed)


def test_stale_rows_are_caught_not_evaluated(local_mlflow, repo_root):
    from abx.evaluate import DatasetMismatchError, ensure_dataset

    seed = [r for r in load_seed(repo_root / "evals" / "seed.jsonl") if r.id in SUBSET]
    ensure_dataset("c.s.reused", seed, "responses", local_mlflow, _local_exists)
    # A question removed from the seed would linger in an upsert-only dataset.
    with pytest.raises(DatasetMismatchError, match="has 5 rows, the seed has 4"):
        ensure_dataset("c.s.reused", seed[:4], "responses", local_mlflow, _local_exists)


@scorer(name="relevance_to_query")
def always_relevant(inputs):
    return "yes"


def test_full_path_from_dataset_to_gate_summary(local_mlflow, repo_root):
    from abx.evaluate import build_scorers, ensure_dataset, evaluate_dataset

    seed = [r for r in load_seed(repo_root / "evals" / "seed.jsonl") if r.id in SUBSET]
    dataset = ensure_dataset("c.s.full_path", seed, "responses", local_mlflow, _local_exists)
    judges = {
        "correctness": strict_correctness,
        "relevance_to_query": always_relevant,
        "expectations_guidelines": strict_guidelines,
        "safety": fake_safety,
        "retrieval_groundedness": no_retriever,
    }
    summary = evaluate_dataset(
        dataset,
        "c.s.full_path",
        seed,
        predict_fn=stub_agent,
        scorers=build_scorers(judges),
        run_name="contract",
        tags={"abx.endpoint": "stub"},
    )
    # Tags written into the managed dataset reach the result rows too.
    assert summary.unknown_rows == 0 and summary.missing_ids == []
    assert summary.dataset_fqn == "c.s.full_path"
    assert summary.rows_by_kind == {"direct": 2, "multi_doc": 1, "out_of_scope": 2}
    assert summary.correctness_mean == 1.0
    assert summary.relevance_mean == 1.0
    assert summary.out_of_scope_refusal_rate == 1.0
