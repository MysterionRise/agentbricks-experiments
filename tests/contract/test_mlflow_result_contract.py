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
