"""The Asset Bundle and the entry point, checked offline.

`databricks bundle validate` needs workspace credentials, so these tests cover the
mistakes it would not catch anyway: a serverless environment whose Python is older
than the package allows, a wheel path that resolves to the wrong folder, and an
entry point whose failure does not fail the job.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
import yaml

from abx import cli

# Serverless environment version -> Python it runs (Databricks release notes).
SERVERLESS_PYTHON = {"3": (3, 12), "4": (3, 12)}


def _jobs(repo_root: Path) -> dict:
    return yaml.safe_load((repo_root / "resources" / "jobs.yml").read_text())["resources"]["jobs"]


def _environments(repo_root: Path):
    for job_name, job in _jobs(repo_root).items():
        for env in job.get("environments", []):
            yield job_name, env["spec"]


def test_every_environment_runs_a_supported_python(repo_root: Path):
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text())
    minimum = tuple(int(x) for x in pyproject["project"]["requires-python"].lstrip(">=").split("."))
    envs = list(_environments(repo_root))
    assert envs, "no job environments found"
    for job_name, spec in envs:
        assert "client" not in spec, f"{job_name}: `client` is deprecated; use environment_version"
        version = str(spec.get("environment_version"))
        assert version in SERVERLESS_PYTHON, f"{job_name}: unknown environment {version!r}"
        assert SERVERLESS_PYTHON[version] >= minimum, f"{job_name}: Python too old"


def test_wheel_dependencies_resolve_to_bundle_dist(repo_root: Path):
    resources = repo_root / "resources"
    for job_name, spec in _environments(repo_root):
        wheels = [d for d in spec["dependencies"] if d.endswith(".whl")]
        assert wheels, f"{job_name}: no wheel dependency"
        for dep in wheels:
            # Bundle paths resolve relative to the file that declares them.
            resolved = (resources / dep).parent.resolve()
            assert resolved == (repo_root / "dist").resolve(), f"{job_name}: {dep} -> {resolved}"


def test_cost_job_reads_thresholds_from_the_synced_pyproject(repo_root: Path):
    params = _jobs(repo_root)["cost_job"]["tasks"][0]["python_wheel_task"]["parameters"]
    assert "--pyproject" in params


def test_bundle_wheel_version_is_unique_per_deploy(repo_root: Path):
    bundle = yaml.safe_load((repo_root / "databricks.yml").read_text())
    assert bundle["artifacts"]["abx_wheel"]["dynamic_version"] is True


def test_console_script_is_the_exit_code_wrapper(repo_root: Path):
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text())
    assert pyproject["project"]["scripts"]["abx"] == "abx.cli:run"


@pytest.mark.parametrize(("outcome", "expected"), [(0, 0), (1, 1), (2, 2)])
def test_run_exits_with_main_code(monkeypatch, outcome, expected):
    monkeypatch.setattr(cli, "main", lambda: outcome)
    with pytest.raises(SystemExit) as exc:
        cli.run()
    assert exc.value.code == expected


def test_run_maps_unexpected_errors_to_2_not_gate_failure(monkeypatch):
    def boom() -> int:
        raise RuntimeError("workspace unreachable")

    monkeypatch.setattr(cli, "main", boom)
    with pytest.raises(SystemExit) as exc:
        cli.run()
    assert exc.value.code == 2
