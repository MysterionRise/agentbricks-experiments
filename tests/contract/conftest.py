"""Fixtures for the MLflow contract tests: a real, offline MLflow on sqlite."""

from __future__ import annotations

import mlflow
import pytest


@pytest.fixture
def local_mlflow(tmp_path, monkeypatch):
    """Point MLflow at a throwaway sqlite store and experiment under tmp_path."""
    monkeypatch.setenv("MLFLOW_DISABLE_TELEMETRY", "true")
    monkeypatch.setenv("MLFLOW_DISABLE_AGENT_HINT", "1")
    monkeypatch.chdir(tmp_path)
    previous = mlflow.get_tracking_uri()
    mlflow.set_tracking_uri(f"sqlite:///{tmp_path}/mlflow.db")
    experiment_id = mlflow.create_experiment(
        "abx-contract", artifact_location=(tmp_path / "artifacts").as_uri()
    )
    mlflow.set_experiment(experiment_id=experiment_id)
    yield experiment_id
    while mlflow.active_run() is not None:
        mlflow.end_run()
    mlflow.set_tracking_uri(previous)
