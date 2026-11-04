from pathlib import Path

import pandas as pd
import pytest

from abx.gate import EvalSummary, GateThresholds, RowVerdict, apply_gate, summarize
from abx.seed import SeedRecord, build_request

THRESHOLDS = GateThresholds(
    min_correctness_mean=0.8,
    min_relevance_mean=0.85,
    min_out_of_scope_refusal_rate=0.9,
    max_safety_failures=0,
    min_rows_evaluated=3,
)

SEED = [
    SeedRecord(id="q1", kind="direct", question="Question one?", expected_facts=["a"]),
    SeedRecord(
        id="q2",
        kind="multi_doc",
        question="Question two?",
        expected_facts=["b"],
        source_docs=["x", "y"],
    ),
    SeedRecord(id="q3", kind="out_of_scope", question="Question three?", guidelines=["refuse"]),
    SeedRecord(id="q4", kind="direct", question="Question four?", expected_facts=["c"]),
]
BY_ID = {r.id: r for r in SEED}


def _row(seed_id: str, *, tags: object = "default", state: str = "OK", **scores: object):
    """One row shaped like MLflow 3.17's result_df (see tests/contract)."""
    record = BY_ID.get(seed_id)
    question = record.question if record else seed_id
    row: dict[str, object] = {
        "trace_id": f"tr-{seed_id}",
        "request": build_request(question, "responses"),
        "response": {"output": []},
        "state": state,
        "tags": {"seed_id": seed_id, "kind": record.kind if record else "direct", "mlflow.x": "y"}
        if tags == "default"
        else tags,
        # MLflow logs dataset expectations as columns too; the gate must ignore them.
        "expected_facts/value": ["a fact"],
        "guidelines/value": None,
    }
    for name, value in scores.items():
        row[f"{name}/value"] = value
        row[f"{name}/rationale"] = f"because {name}"
    return row


def test_repo_thresholds_load(repo_root: Path):
    t = GateThresholds.from_pyproject(repo_root / "pyproject.toml")
    assert 0 < t.min_correctness_mean <= 1
    assert t.min_rows_evaluated >= 30


def test_missing_gate_table(tmp_path: Path):
    p = tmp_path / "pyproject.toml"
    p.write_text("[tool.other]\nx = 1\n")
    with pytest.raises(ValueError, match=r"tool\.abx\.gate"):
        GateThresholds.from_pyproject(p)


def test_summarize_per_kind():
    df = pd.DataFrame(
        [
            _row(
                "q1",
                correctness="yes",
                relevance_to_query="yes",
                safety="yes",
                retrieval_groundedness="yes",
            ),
            _row(
                "q2",
                correctness="no",
                relevance_to_query="yes",
                safety="yes",
                retrieval_groundedness=True,
            ),
            _row("q3", expectations_guidelines="yes", relevance_to_query="no", safety="yes"),
            _row("q4", correctness=1, relevance_to_query="yes", safety="no"),
        ]
    )
    s = summarize("run-1", df, SEED, dataset_fqn="main.ab.ds")
    assert s.rows == 4
    assert s.rows_by_kind == {"direct": 2, "multi_doc": 1, "out_of_scope": 1}
    assert s.missing_ids == [] and s.unknown_rows == 0 and s.errored_rows == 0
    assert s.dataset_fqn == "main.ab.ds"
    assert s.correctness_mean == pytest.approx(2 / 3)
    # Relevance is scoped to answerable rows: q3's "no" on a refusal is ignored.
    assert s.relevance_mean == 1.0
    # Groundedness is report-only: q4's missing verdict is skipped, not failed.
    assert s.groundedness_mean == 1.0
    assert s.judge_errors == {"retrieval_groundedness": 1}
    assert s.out_of_scope_refusal_rate == 1.0
    assert s.safety_failures == 1
    # expected_facts/value and guidelines/value are not judges.
    for verdict in s.worst:
        assert set(verdict.scores) <= {
            "correctness",
            "relevance_to_query",
            "expectations_guidelines",
            "safety",
            "retrieval_groundedness",
        }
    assert {r.question for r in s.worst} == {"Question two?", "Question four?"}
    assert all(r.rationale.startswith("because") for r in s.worst)


def test_kind_comes_from_tags_not_from_an_inputs_column():
    """Regression: MLflow 3.17 has no `inputs` column; the gate read it and saw nothing."""
    df = pd.DataFrame([_row("q1", correctness="yes", safety="yes")])
    assert "inputs" not in df.columns
    s = summarize("r", df, SEED)
    assert s.rows_by_kind == {"direct": 1}
    assert s.unknown_rows == 0


def test_falls_back_to_the_question_when_tags_are_missing():
    df = pd.DataFrame([_row("q3", tags={}, expectations_guidelines="yes", safety="yes")])
    s = summarize("r", df, SEED)
    assert s.rows_by_kind == {"out_of_scope": 1}


def test_tags_as_json_string_are_accepted():
    df = pd.DataFrame([_row("q1", tags='{"seed_id": "q1", "kind": "direct"}', safety="yes")])
    assert summarize("r", df, SEED).rows_by_kind == {"direct": 1}


def test_kind_mismatch_between_tags_and_seed_is_unknown():
    df = pd.DataFrame([_row("q1", tags={"seed_id": "q1", "kind": "out_of_scope"}, safety="yes")])
    s = summarize("r", df, SEED)
    assert s.unknown_rows == 1
    assert any("could not be matched" in r for r in apply_gate(s, THRESHOLDS).reasons)


def test_unknown_rows_and_missing_seed_ids_fail_the_gate():
    df = pd.DataFrame([_row("Unknown?", tags={}, correctness=float("nan"), safety=None)])
    s = summarize("r", df, SEED)
    assert s.rows_by_kind == {"unknown": 1}
    assert s.unknown_rows == 1
    assert s.missing_ids == ["q1", "q2", "q3", "q4"]
    reasons = "\n".join(apply_gate(s, THRESHOLDS).reasons)
    assert "4 seed rows missing from results: q1, q2, q3, q4" in reasons
    assert "1 result rows could not be matched" in reasons


def test_errored_traces_fail_the_gate():
    df = pd.DataFrame([_row("q1", state="ERROR", correctness="yes", safety="yes")])
    s = summarize("r", df, SEED)
    assert s.errored_rows == 1
    assert any("ended in ERROR" in r for r in apply_gate(s, THRESHOLDS).reasons)


def test_missing_gated_verdict_counts_as_failure():
    """Fail closed: a judge error must not shrink the denominator (ADR 0002)."""
    df = pd.DataFrame(
        [
            _row("q1", correctness="yes", relevance_to_query="yes", safety="yes"),
            _row("q4", correctness=float("nan"), relevance_to_query="yes", safety="yes"),
        ]
    )
    df.loc[1, "correctness/error_message"] = "judge timed out"
    s = summarize("r", df, SEED)
    assert s.correctness_mean == 0.5
    assert s.judge_errors["correctness"] == 1
    worst = {w.question: w for w in s.worst}
    assert worst["Question four?"].scores["correctness"] is None
    assert worst["Question four?"].rationale == "judge timed out"


def test_absent_judge_column_fails_every_applicable_row():
    df = pd.DataFrame([_row("q1", safety="yes"), _row("q4", safety="yes")])
    s = summarize("r", df, SEED)
    assert s.correctness_mean == 0.0
    assert s.judge_errors["correctness"] == 2


def test_missing_safety_verdict_fails_the_gate():
    df = pd.DataFrame([_row("q1", correctness="yes", relevance_to_query="yes", safety=None)])
    s = summarize("r", df, SEED)
    assert s.safety_failures == 0
    reasons = apply_gate(s, THRESHOLDS).reasons
    assert any("1 rows without a safety verdict" in r for r in reasons)


def test_judges_ignore_rows_they_do_not_apply_to():
    df = pd.DataFrame(
        [
            _row(
                "q3",
                expectations_guidelines="yes",
                correctness="no",
                relevance_to_query="no",
                safety="yes",
            )
        ]
    )
    s = summarize("r", df, SEED)
    assert s.correctness_mean is None and s.relevance_mean is None
    assert s.out_of_scope_refusal_rate == 1.0
    assert s.worst == []


def test_gate_passes():
    s = EvalSummary("r", 40, {}, 0.9, 0.95, 0.9, 1.0, 0)
    v = apply_gate(s, THRESHOLDS)
    assert v.passed and v.reasons == []


def test_gate_reports_every_failure():
    s = EvalSummary("r", 2, {}, 0.5, None, None, 0.5, 2)
    v = apply_gate(s, THRESHOLDS)
    assert not v.passed
    joined = "\n".join(v.reasons)
    assert "only 2 rows" in joined
    assert "correctness mean 0.50 below 0.80" in joined
    assert "relevance mean unavailable" in joined
    assert "out-of-scope refusal rate 0.50 below 0.90" in joined
    assert "2 safety failures" in joined


def test_summary_round_trip():
    s = EvalSummary(
        "r",
        1,
        {"direct": 1},
        1.0,
        1.0,
        None,
        None,
        0,
        worst=[RowVerdict("Q", "direct", {"correctness": False}, "why")],
        dataset_fqn="c.s.d",
        missing_ids=["x"],
        unknown_rows=1,
        errored_rows=2,
        judge_errors={"safety": 1},
    )
    assert EvalSummary.from_dict(s.as_dict()) == s


def test_summary_reads_json_written_before_the_new_fields():
    old = {
        "run_id": "r",
        "rows": 1,
        "rows_by_kind": {},
        "correctness_mean": None,
        "relevance_mean": None,
        "groundedness_mean": None,
        "out_of_scope_refusal_rate": None,
        "safety_failures": 0,
        "worst": [],
    }
    s = EvalSummary.from_dict(old)
    assert s.missing_ids == [] and s.unknown_rows == 0 and s.dataset_fqn == ""
