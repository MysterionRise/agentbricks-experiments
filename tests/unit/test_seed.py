import json
from pathlib import Path

import pytest

from abx.seed import (
    SeedRecord,
    build_request,
    kinds_by_question,
    load_seed,
    question_from_inputs,
    to_mlflow_records,
)


def test_repo_seed_is_valid(repo_root: Path):
    records = load_seed(repo_root / "evals" / "seed.jsonl")
    kinds = {r.kind for r in records}
    assert kinds == {"direct", "multi_doc", "out_of_scope"}
    assert len(records) >= 30
    assert len({r.id for r in records}) == len(records)


def test_seed_sources_exist_in_corpus(repo_root: Path):
    corpus = {p.stem for p in (repo_root / "data" / "corpus").glob("*.md")}
    for record in load_seed(repo_root / "evals" / "seed.jsonl"):
        missing = set(record.source_docs) - corpus
        assert not missing, f"{record.id} cites unknown docs {missing}"


@pytest.mark.parametrize(
    "row",
    [
        {"id": "x", "kind": "direct", "question": "What is it?"},  # no facts
        {
            "id": "x",
            "kind": "multi_doc",
            "question": "What?",
            "expected_facts": ["a"],
            "source_docs": ["one"],
        },
        {
            "id": "x",
            "kind": "out_of_scope",
            "question": "What?",
            "expected_facts": ["a"],
            "guidelines": ["g"],
        },
        {"id": "x", "kind": "out_of_scope", "question": "What?"},  # no guideline
        {"id": "x", "kind": "weird", "question": "What?"},
    ],
)
def test_invalid_rows_rejected(row):
    with pytest.raises(ValueError):
        SeedRecord.model_validate(row)


def test_duplicate_ids_rejected(tmp_path: Path):
    row = {"id": "a", "kind": "direct", "question": "Question?", "expected_facts": ["f"]}
    path = tmp_path / "seed.jsonl"
    path.write_text("\n".join([json.dumps(row), json.dumps(row)]))
    with pytest.raises(ValueError, match="duplicate id"):
        load_seed(path)


def test_empty_seed_rejected(tmp_path: Path):
    path = tmp_path / "seed.jsonl"
    path.write_text("\n\n")
    with pytest.raises(ValueError, match="empty"):
        load_seed(path)


def test_bad_json_reports_line(tmp_path: Path):
    path = tmp_path / "seed.jsonl"
    path.write_text('{"id": "a"}\nnot json\n')
    with pytest.raises(ValueError, match=":1:"):
        load_seed(path)


def test_request_shapes_round_trip():
    for shape in ("responses", "chat"):
        payload = build_request("How many days?", shape)
        assert question_from_inputs(payload) == "How many days?"
    assert question_from_inputs({"question": "plain"}) == "plain"
    assert question_from_inputs({}) is None
    assert question_from_inputs({"input": "not a list"}) is None


def test_to_mlflow_records_shapes_expectations():
    records = [
        SeedRecord(id="d", kind="direct", question="Direct?", expected_facts=["f1"]),
        SeedRecord(id="o", kind="out_of_scope", question="Scope?", guidelines=["refuse"]),
    ]
    out = to_mlflow_records(records, "responses")
    assert out[0]["inputs"] == {"input": [{"role": "user", "content": "Direct?"}]}
    assert out[0]["expectations"] == {"expected_facts": ["f1"]}
    assert out[0]["tags"] == {"seed_id": "d", "kind": "direct"}
    assert out[1]["expectations"] == {"guidelines": ["refuse"]}
    assert kinds_by_question(records) == {"Direct?": "direct", "Scope?": "out_of_scope"}
