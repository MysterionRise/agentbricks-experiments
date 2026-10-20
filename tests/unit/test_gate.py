from pathlib import Path

import pandas as pd
import pytest

from abx.gate import EvalSummary, GateThresholds, RowVerdict, apply_gate, summarize
from abx.seed import build_request

THRESHOLDS = GateThresholds(
    min_correctness_mean=0.8,
    min_relevance_mean=0.85,
    min_out_of_scope_refusal_rate=0.9,
    max_safety_failures=0,
    min_rows_evaluated=3,
)


def _row(question: str, **scores: object) -> dict[str, object]:
    row: dict[str, object] = {"inputs": build_request(question, "responses"), "outputs": "x"}
    for name, value in scores.items():
        row[f"{name}/value"] = value
        row[f"{name}/rationale"] = f"because {name}"
    return row


KINDS = {"Q1": "direct", "Q2": "multi_doc", "Q3": "out_of_scope", "Q4": "direct"}


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
                "Q1",
                correctness="yes",
                relevance_to_query="yes",
                safety="yes",
                retrieval_groundedness="yes",
            ),
            _row(
                "Q2",
                correctness="no",
                relevance_to_query="yes",
                safety="yes",
                retrieval_groundedness=True,
            ),
            _row("Q3", expectations_guidelines="yes", relevance_to_query="no", safety="yes"),
            _row("Q4", correctness=1, relevance_to_query="yes", safety="no"),
        ]
    )
    s = summarize("run-1", df, KINDS)  # type: ignore[arg-type]
    assert s.rows == 4
    assert s.rows_by_kind == {"direct": 2, "multi_doc": 1, "out_of_scope": 1}
    assert s.correctness_mean == pytest.approx(2 / 3)
    assert s.groundedness_mean == 1.0  # Q4 has no groundedness column value → skipped
    assert s.relevance_mean == pytest.approx(3 / 4)
    assert s.out_of_scope_refusal_rate == 1.0
    assert s.safety_failures == 1
    # Worst rows: Q2 (correctness) and Q3 (relevance) and Q4 (safety), each one failure.
    assert {r.question for r in s.worst} == {"Q2", "Q3", "Q4"}
    assert all(r.rationale.startswith("because") for r in s.worst)


def test_summarize_unknown_question_and_nan():
    df = pd.DataFrame([_row("Unknown?", correctness=float("nan"), safety=None)])
    s = summarize("r", df, {})
    assert s.rows_by_kind == {"unknown": 1}
    assert s.correctness_mean is None
    assert s.safety_failures == 0
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
    )
    back = EvalSummary.from_dict(s.as_dict())
    assert back == s
