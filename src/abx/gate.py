"""Turn an evaluation result into a pass/fail verdict.

This module is pure: it takes a DataFrame and thresholds and returns numbers.
Everything that talks to MLflow lives in ``evaluate.py`` so the gate itself is
unit-tested without a workspace.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from abx.seed import ANSWERABLE, Kind, question_from_inputs

if TYPE_CHECKING:
    from pathlib import Path

    import pandas as pd

PASS_VALUES = frozenset({"yes", "true", "pass", "1"})

CORRECTNESS = "correctness"
RELEVANCE = "relevance_to_query"
GUIDELINES = "expectations_guidelines"
SAFETY = "safety"
GROUNDEDNESS = "retrieval_groundedness"


class GateThresholds(BaseModel):
    """Thresholds read from ``[tool.abx.gate]`` in pyproject.toml."""

    min_correctness_mean: float = Field(ge=0, le=1)
    min_relevance_mean: float = Field(ge=0, le=1)
    min_out_of_scope_refusal_rate: float = Field(ge=0, le=1)
    max_safety_failures: int = Field(ge=0)
    min_rows_evaluated: int = Field(ge=1)

    @classmethod
    def from_pyproject(cls, path: Path) -> GateThresholds:
        """Load thresholds; a missing table is a configuration error, not a default."""
        with path.open("rb") as fh:
            data = tomllib.load(fh)
        try:
            table = data["tool"]["abx"]["gate"]
        except KeyError as exc:
            msg = f"{path}: missing [tool.abx.gate]"
            raise ValueError(msg) from exc
        return cls.model_validate(table)


@dataclass(frozen=True)
class RowVerdict:
    """What the judges said about one question, kept for the report."""

    question: str
    kind: Kind | None
    scores: Mapping[str, bool | None]
    rationale: str


@dataclass(frozen=True)
class EvalSummary:
    """Per-scorer rates, overall and per kind, plus the worst rows."""

    run_id: str
    rows: int
    rows_by_kind: Mapping[str, int]
    correctness_mean: float | None
    relevance_mean: float | None
    groundedness_mean: float | None
    out_of_scope_refusal_rate: float | None
    safety_failures: int
    worst: list[RowVerdict] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """JSON-friendly form, written next to the report so `abx cost` can reuse it."""
        return {
            "run_id": self.run_id,
            "rows": self.rows,
            "rows_by_kind": dict(self.rows_by_kind),
            "correctness_mean": self.correctness_mean,
            "relevance_mean": self.relevance_mean,
            "groundedness_mean": self.groundedness_mean,
            "out_of_scope_refusal_rate": self.out_of_scope_refusal_rate,
            "safety_failures": self.safety_failures,
            "worst": [
                {
                    "question": r.question,
                    "kind": r.kind,
                    "scores": dict(r.scores),
                    "rationale": r.rationale,
                }
                for r in self.worst
            ],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EvalSummary:
        """Inverse of ``as_dict``."""
        worst = [
            RowVerdict(
                question=str(r["question"]),
                kind=r.get("kind"),
                scores=dict(r.get("scores", {})),
                rationale=str(r.get("rationale", "")),
            )
            for r in data.get("worst", [])
        ]
        return cls(
            run_id=str(data["run_id"]),
            rows=int(data["rows"]),
            rows_by_kind=dict(data.get("rows_by_kind", {})),
            correctness_mean=data.get("correctness_mean"),
            relevance_mean=data.get("relevance_mean"),
            groundedness_mean=data.get("groundedness_mean"),
            out_of_scope_refusal_rate=data.get("out_of_scope_refusal_rate"),
            safety_failures=int(data.get("safety_failures", 0)),
            worst=worst,
        )


@dataclass(frozen=True)
class GateVerdict:
    """Pass/fail with one reason per failed threshold."""

    passed: bool
    reasons: list[str]


def _as_pass(value: object) -> bool | None:
    """Normalise a judge value: yes/no strings, booleans, 0/1. None when absent."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        if value != value:  # NaN
            return None
        return value >= 1
    text = str(value).strip().lower()
    if text in ("", "nan", "none"):
        return None
    return text in PASS_VALUES


def _rate(values: list[bool | None]) -> float | None:
    known = [v for v in values if v is not None]
    if not known:
        return None
    return sum(1 for v in known if v) / len(known)


def _scorer_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map scorer name → column holding its value, tolerant to MLflow naming."""
    columns: dict[str, str] = {}
    for col in df.columns:
        name = str(col)
        if name.endswith("/value"):
            columns[name.removesuffix("/value")] = name
    return columns


def _rationale(df_row: pd.Series[Any], scorer: str) -> str:
    for suffix in ("/rationale", "/reason"):
        key = f"{scorer}{suffix}"
        if key in df_row.index:
            value = df_row[key]
            if isinstance(value, str):
                return value
    return ""


def summarize(
    run_id: str,
    result_df: pd.DataFrame,
    kinds: Mapping[str, Kind],
    worst_n: int = 3,
) -> EvalSummary:
    """Compute per-kind rates from the evaluation DataFrame."""
    columns = _scorer_columns(result_df)
    rows_by_kind: dict[str, int] = {}
    correctness: list[bool | None] = []
    relevance: list[bool | None] = []
    groundedness: list[bool | None] = []
    refusals: list[bool | None] = []
    safety_failures = 0
    verdicts: list[tuple[int, RowVerdict]] = []

    for _, row in result_df.iterrows():
        inputs = row.get("inputs")
        question = question_from_inputs(inputs) if isinstance(inputs, Mapping) else None
        kind = kinds.get(question) if question is not None else None
        rows_by_kind[kind or "unknown"] = rows_by_kind.get(kind or "unknown", 0) + 1

        scores = {scorer: _as_pass(row[col]) for scorer, col in columns.items() if col in row.index}
        if kind in ANSWERABLE:
            correctness.append(scores.get(CORRECTNESS))
            groundedness.append(scores.get(GROUNDEDNESS))
        if kind == "out_of_scope":
            refusals.append(scores.get(GUIDELINES))
        relevance.append(scores.get(RELEVANCE))
        if scores.get(SAFETY) is False:
            safety_failures += 1

        failed = [s for s, v in scores.items() if v is False]
        rationale = _rationale(row, failed[0]) if failed else ""
        verdicts.append(
            (len(failed), RowVerdict(question or "?", kind, scores, rationale)),
        )

    verdicts.sort(key=lambda item: item[0], reverse=True)
    worst = [v for n, v in verdicts[:worst_n] if n > 0]

    return EvalSummary(
        run_id=run_id,
        rows=len(result_df),
        rows_by_kind=rows_by_kind,
        correctness_mean=_rate(correctness),
        relevance_mean=_rate(relevance),
        groundedness_mean=_rate(groundedness),
        out_of_scope_refusal_rate=_rate(refusals),
        safety_failures=safety_failures,
        worst=worst,
    )


def apply_gate(summary: EvalSummary, thresholds: GateThresholds) -> GateVerdict:
    """Compare the summary against every threshold. Missing metrics fail the gate."""
    reasons: list[str] = []

    if summary.rows < thresholds.min_rows_evaluated:
        reasons.append(f"only {summary.rows} rows evaluated (min {thresholds.min_rows_evaluated})")

    checks: list[tuple[str, float | None, float]] = [
        ("correctness mean", summary.correctness_mean, thresholds.min_correctness_mean),
        ("relevance mean", summary.relevance_mean, thresholds.min_relevance_mean),
        (
            "out-of-scope refusal rate",
            summary.out_of_scope_refusal_rate,
            thresholds.min_out_of_scope_refusal_rate,
        ),
    ]
    for label, value, minimum in checks:
        if value is None:
            reasons.append(f"{label} unavailable (no judge output)")
        elif value < minimum:
            reasons.append(f"{label} {value:.2f} below {minimum:.2f}")

    if summary.safety_failures > thresholds.max_safety_failures:
        reasons.append(
            f"{summary.safety_failures} safety failures (max {thresholds.max_safety_failures})"
        )

    return GateVerdict(passed=not reasons, reasons=reasons)
