from pathlib import Path

import pytest

from abx import cli


def test_validate_passes_on_repo(repo_root: Path):
    assert cli.main(["validate"]) == 0


def test_validate_fails_when_seed_too_small(tmp_path: Path, repo_root: Path):
    seed = tmp_path / "seed.jsonl"
    seed.write_text('{"id":"a","kind":"direct","question":"Question?","expected_facts":["f"]}\n')
    assert cli.main(["validate", "--seed", str(seed)]) == 2


def test_parser_requires_command():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_eval_exit_codes(monkeypatch, tmp_path: Path):
    """The gate verdict decides the exit code; everything remote is stubbed."""
    from abx import evaluate, ka
    from abx.gate import EvalSummary

    monkeypatch.setattr("databricks.sdk.WorkspaceClient", lambda: object())
    monkeypatch.setattr(ka, "resolve_endpoint_name", lambda w, s: "ep")

    good = EvalSummary("r", 40, {}, 1.0, 1.0, 1.0, 1.0, 0)
    monkeypatch.setattr(evaluate, "run_evaluation", lambda *a, **k: good)
    assert cli.main(["eval", "--out", str(tmp_path), "--no-volume"]) == 0
    assert (tmp_path / "latest.md").exists()

    bad = EvalSummary("r", 40, {}, 0.1, 1.0, 1.0, 1.0, 0)
    monkeypatch.setattr(evaluate, "run_evaluation", lambda *a, **k: bad)
    assert cli.main(["eval", "--out", str(tmp_path), "--no-volume"]) == 1


def test_cost_keeps_previous_eval(monkeypatch, tmp_path: Path):
    from abx import cost as cost_mod
    from abx import ka
    from abx.cost import CostSummary
    from abx.gate import EvalSummary
    from abx.report import write_local

    write_local(tmp_path, "", EvalSummary("r", 40, {}, 1.0, 1.0, 1.0, 1.0, 0))
    monkeypatch.setattr("databricks.sdk.WorkspaceClient", lambda: object())
    monkeypatch.setattr(ka, "resolve_endpoint_name", lambda w, s: "ep")
    monkeypatch.setattr(
        cost_mod, "fetch_cost", lambda w, s, e: CostSummary(e, 7, True, requests=5, usd_list=1.0)
    )
    assert cli.main(["cost", "--out", str(tmp_path), "--no-volume"]) == 0
    text = (tmp_path / "latest.md").read_text()
    assert "**Verdict: PASS**" in text
    assert "| Requests | 5 |" in text
