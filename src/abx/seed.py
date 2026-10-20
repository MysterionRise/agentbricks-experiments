"""The hand-written evaluation seed and its conversion into MLflow dataset records.

``evals/seed.jsonl`` is the single source of truth for what "good" means. It is
validated on load so a malformed row fails in CI, not in the workspace. The seed
is never fed to the assistant as examples: it is a held-out test set.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

Kind = Literal["direct", "multi_doc", "out_of_scope"]
RequestShape = Literal["responses", "chat"]

KINDS: tuple[Kind, ...] = ("direct", "multi_doc", "out_of_scope")
ANSWERABLE: tuple[Kind, ...] = ("direct", "multi_doc")


class SeedRecord(BaseModel):
    """One evaluation question with what a correct answer must contain."""

    id: str = Field(min_length=1)
    kind: Kind
    question: str = Field(min_length=5)
    expected_facts: list[str] = Field(default_factory=list)
    guidelines: list[str] = Field(default_factory=list)
    source_docs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_shape(self) -> SeedRecord:
        if self.kind in ANSWERABLE and not self.expected_facts:
            msg = f"{self.id}: {self.kind} rows need at least one expected fact"
            raise ValueError(msg)
        if self.kind == "multi_doc" and len(self.source_docs) < 2:
            msg = f"{self.id}: multi_doc rows must cite at least two source docs"
            raise ValueError(msg)
        if self.kind == "out_of_scope":
            if self.expected_facts:
                msg = f"{self.id}: out_of_scope rows must not carry expected facts"
                raise ValueError(msg)
            if not self.guidelines:
                msg = f"{self.id}: out_of_scope rows need a guideline for the judge"
                raise ValueError(msg)
        return self


def load_seed(path: Path) -> list[SeedRecord]:
    """Read and validate the JSONL seed. Ids must be unique."""
    records: list[SeedRecord] = []
    seen: set[str] = set()
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            record = SeedRecord.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError) as exc:
            msg = f"{path}:{line_no}: {exc}"
            raise ValueError(msg) from exc
        if record.id in seen:
            msg = f"{path}:{line_no}: duplicate id {record.id!r}"
            raise ValueError(msg)
        seen.add(record.id)
        records.append(record)
    if not records:
        msg = f"{path}: seed is empty"
        raise ValueError(msg)
    return records


def build_request(question: str, shape: RequestShape) -> dict[str, Any]:
    """Build the payload the serving endpoint expects for one question.

    Knowledge Assistant endpoints accept the Responses-style ``input`` list. The
    ``chat`` shape is kept for endpoints that still take ``messages``. Confirm the
    shape with Playground → Get code and set ``ABX_REQUEST_SHAPE`` accordingly.
    """
    message = {"role": "user", "content": question}
    if shape == "responses":
        return {"input": [message]}
    return {"messages": [message]}


def question_from_inputs(inputs: Mapping[str, Any]) -> str | None:
    """Recover the question text from an endpoint payload, whatever its shape."""
    for key in ("input", "messages"):
        messages = inputs.get(key)
        if isinstance(messages, list) and messages:
            content = messages[-1].get("content") if isinstance(messages[-1], dict) else None
            if isinstance(content, str):
                return content
    question = inputs.get("question")
    return question if isinstance(question, str) else None


def to_mlflow_records(records: Iterable[SeedRecord], shape: RequestShape) -> list[dict[str, Any]]:
    """Convert seed rows into the ``inputs`` / ``expectations`` dicts MLflow stores."""
    out: list[dict[str, Any]] = []
    for record in records:
        expectations: dict[str, Any] = {}
        if record.expected_facts:
            expectations["expected_facts"] = list(record.expected_facts)
        if record.guidelines:
            expectations["guidelines"] = list(record.guidelines)
        out.append(
            {
                "inputs": build_request(record.question, shape),
                "expectations": expectations,
                "tags": {"seed_id": record.id, "kind": record.kind},
            }
        )
    return out


def kinds_by_question(records: Iterable[SeedRecord]) -> dict[str, Kind]:
    """Map question text to its kind, for joining eval rows back to the seed."""
    return {record.question: record.kind for record in records}
