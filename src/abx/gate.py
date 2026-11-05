"""Turn an evaluation result into a pass/fail verdict.

This module is pure: it takes a DataFrame and thresholds and returns numbers.
Everything that talks to MLflow lives in ``evaluate.py`` so the gate itself is
unit-tested without a workspace.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from abx.seed import ANSWERABLE, KINDS, Kind, SeedRecord, question_from_inputs

if TYPE_CHECKING:
    from pathlib import Path

    import pandas as pd

PASS_VALUES = frozenset({"yes", "true", "pass", "1"})

CORRECTNESS = "correctness"
RELEVANCE = "relevance_to_query"
GUIDELINES = "expectations_guidelines"
SAFETY = "safety"
GROUNDEDNESS = "retrieval_groundedness"

# The only result columns the gate reads as judge verdicts. MLflow also writes
# dataset expectations as ``expected_facts/value`` and ``guidelines/value``;
# those are inputs to the judges, not verdicts.
SCORERS: tuple[str, ...] = (CORRECTNESS, RELEVANCE, GUIDELINES, SAFETY, GROUNDEDNESS)

# Which kinds of question each judge applies to. A correct refusal is not
# "relevant" to the question it declines, so relevance is scoped to answerable
# rows; see the 2026-11-04 amendment to ADR 0002.
APPLIES: dict[str, frozenset[str]] = {
    CORRECTNESS: frozenset(ANSWERABLE),
    RELEVANCE: frozenset(ANSWERABLE),
    GROUNDEDNESS: frozenset(ANSWERABLE),
    GUIDELINES: frozenset({"out_of_scope"}),
    SAFETY: frozenset(KINDS),
}

# Judges whose missing verdict counts as a failure. Groundedness is reported
# only, because a trace may carry no retriever spans for it to read.
GATED: frozenset[str] = frozenset({CORRECTNESS, RELEVANCE, GUIDELINES, SAFETY})


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
    """Per-scorer rates, overall and per kind, plus the worst rows.

    ``missing_ids`` are seed rows with no result row (a lost trace drops a row
    silently). ``unknown_rows`` could not be matched to the seed. ``errored_rows``
    are rows whose trace ended in ERROR. Each of them fails the gate.

    Rates are over the rows each judge applies to. For gated judges a missing
    verdict (judge error, timeout, absent column) counts as a failure and is also
    counted in ``judge_errors``, so an outage cannot pass the gate on a few rows.
    """

    run_id: str
    rows: int
    rows_by_kind: Mapping[str, int]
    correctness_mean: float | None
    relevance_mean: float | None
    groundedness_mean: float | None
    out_of_scope_refusal_rate: float | None
    safety_failures: int
    worst: list[RowVerdict] = field(default_factory=list)
    dataset_fqn: str = ""
    missing_ids: list[str] = field(default_factory=list)
    unknown_rows: int = 0
    errored_rows: int = 0
    judge_errors: Mapping[str, int] = field(default_factory=dict)

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
            "dataset_fqn": self.dataset_fqn,
            "missing_ids": list(self.missing_ids),
            "unknown_rows": self.unknown_rows,
            "errored_rows": self.errored_rows,
            "judge_errors": dict(self.judge_errors),
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
            dataset_fqn=str(data.get("dataset_fqn", "")),
            missing_ids=list(data.get("missing_ids", [])),
            unknown_rows=int(data.get("unknown_rows", 0)),
            errored_rows=int(data.get("errored_rows", 0)),
            judge_errors={str(k): int(v) for k, v in data.get("judge_errors", {}).items()},
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


def _strict_rate(values: list[bool | None]) -> float | None:
    """Share of passes over every applicable row; a missing verdict is a failure."""
    if not values:
        return None
    return sum(1 for v in values if v is True) / len(values)


def _known_rate(values: list[bool | None]) -> float | None:
    """Share of passes over rows with a verdict; for report-only judges."""
    known = [v for v in values if v is not None]
    if not known:
        return None
    return sum(1 for v in known if v) / len(known)


def _scorer_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map each known judge to its ``<name>/value`` column, when present."""
    present = {str(col) for col in df.columns}
    return {name: f"{name}/value" for name in SCORERS if f"{name}/value" in present}


def _as_mapping(value: object) -> Mapping[str, Any]:
    """Tags and requests arrive as dicts locally; tolerate JSON strings too."""
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, Mapping) else {}
    return {}


def _identify(
    row: pd.Series[Any],
    by_id: Mapping[str, SeedRecord],
    by_question: Mapping[str, SeedRecord],
) -> tuple[SeedRecord | None, str]:
    """Match a result row to its seed record and return it with the question text.

    MLflow copies each dataset record's tags onto its trace, so ``tags.seed_id``
    is the primary key; ``tags.kind`` must agree with the seed. Rows without
    usable tags fall back to the question parsed from ``request``.
    """
    tags = _as_mapping(row.get("tags"))
    request = _as_mapping(row.get("request"))
    question = question_from_inputs(request) or ""
    seed_id = tags.get("seed_id")
    if isinstance(seed_id, str) and seed_id in by_id:
        record = by_id[seed_id]
        tagged_kind = tags.get("kind")
        if tagged_kind is not None and tagged_kind != record.kind:
            return None, question or record.question
        return record, question or record.question
    return by_question.get(question), question


def _is_errored(row: pd.Series[Any]) -> bool:
    state = row.get("state")
    return str(getattr(state, "value", state)).upper() == "ERROR"


def _rationale(df_row: pd.Series[Any], scorer: str, *, missing: bool = False) -> str:
    """The judge's explanation; for a missing verdict, its error message first."""
    order = ("/error_message", "/rationale") if missing else ("/rationale", "/reason")
    for suffix in order:
        key = f"{scorer}{suffix}"
        if key in df_row.index:
            value = df_row[key]
            if isinstance(value, str) and value.strip():
                return value
    return ""


def summarize(
    run_id: str,
    result_df: pd.DataFrame,
    seed: Sequence[SeedRecord],
    dataset_fqn: str = "",
    worst_n: int = 3,
) -> EvalSummary:
    """Compute per-kind rates from MLflow's evaluation result table."""
    columns = _scorer_columns(result_df)
    by_id = {r.id: r for r in seed}
    by_question = {r.question: r for r in seed}
    seen_ids: set[str] = set()
    rows_by_kind: dict[str, int] = {}
    unknown_rows = 0
    errored_rows = 0
    by_judge: dict[str, list[bool | None]] = {name: [] for name in SCORERS}
    judge_errors: dict[str, int] = {}
    safety_failures = 0
    verdicts: list[tuple[int, RowVerdict]] = []

    for _, row in result_df.iterrows():
        record, question = _identify(row, by_id, by_question)
        kind: Kind | None = record.kind if record is not None else None
        if record is None:
            unknown_rows += 1
        else:
            seen_ids.add(record.id)
        if _is_errored(row):
            errored_rows += 1
        rows_by_kind[kind or "unknown"] = rows_by_kind.get(kind or "unknown", 0) + 1

        # Only judges that apply to this row's kind; an unknown row already fails.
        scores: dict[str, bool | None] = {}
        if kind is not None:
            for name in SCORERS:
                if kind not in APPLIES[name]:
                    continue
                col = columns.get(name)
                value = _as_pass(row[col]) if col is not None else None
                scores[name] = value
                by_judge[name].append(value)
                if value is None:
                    judge_errors[name] = judge_errors.get(name, 0) + 1
            if scores.get(SAFETY) is False:
                safety_failures += 1

        failed = [s for s, v in scores.items() if v is False or (v is None and s in GATED)]
        rationale = _rationale(row, failed[0], missing=scores[failed[0]] is None) if failed else ""
        verdicts.append(
            (len(failed), RowVerdict(question or "?", kind, scores, rationale)),
        )

    verdicts.sort(key=lambda item: item[0], reverse=True)
    worst = [v for n, v in verdicts[:worst_n] if n > 0]

    return EvalSummary(
        run_id=run_id,
        rows=len(result_df),
        rows_by_kind=rows_by_kind,
        correctness_mean=_strict_rate(by_judge[CORRECTNESS]),
        relevance_mean=_strict_rate(by_judge[RELEVANCE]),
        groundedness_mean=_known_rate(by_judge[GROUNDEDNESS]),
        out_of_scope_refusal_rate=_strict_rate(by_judge[GUIDELINES]),
        safety_failures=safety_failures,
        worst=worst,
        dataset_fqn=dataset_fqn,
        missing_ids=sorted(set(by_id) - seen_ids),
        unknown_rows=unknown_rows,
        errored_rows=errored_rows,
        judge_errors=judge_errors,
    )


def apply_gate(summary: EvalSummary, thresholds: GateThresholds) -> GateVerdict:
    """Compare the summary against every threshold. Missing metrics fail the gate."""
    reasons: list[str] = []

    if summary.rows < thresholds.min_rows_evaluated:
        reasons.append(f"only {summary.rows} rows evaluated (min {thresholds.min_rows_evaluated})")
    if summary.missing_ids:
        shown = ", ".join(summary.missing_ids[:5])
        more = "" if len(summary.missing_ids) <= 5 else f" and {len(summary.missing_ids) - 5} more"
        reasons.append(f"{len(summary.missing_ids)} seed rows missing from results: {shown}{more}")
    if summary.unknown_rows:
        reasons.append(f"{summary.unknown_rows} result rows could not be matched to the seed")
    if summary.errored_rows:
        reasons.append(f"{summary.errored_rows} rows whose trace ended in ERROR")

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
    # A missing safety verdict is not a pass: the answer was never checked.
    unverified = summary.judge_errors.get(SAFETY, 0)
    if unverified:
        reasons.append(f"{unverified} rows without a safety verdict (judge error)")

    return GateVerdict(passed=not reasons, reasons=reasons)
