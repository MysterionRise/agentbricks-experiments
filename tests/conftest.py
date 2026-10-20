"""Shared fixtures. No test here talks to a workspace or to MLflow tracking."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from abx.config import Settings

# A developer's .env or exported ABX_* variables must not leak into the suite.
Settings.model_config["env_file"] = None
for _key in list(os.environ):
    if _key.startswith("ABX_"):
        os.environ.pop(_key)

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def settings() -> Settings:
    """Default settings, isolated from the environment."""
    return Settings()


@pytest.fixture
def repo_root() -> Path:
    """Path to the repository checkout."""
    return REPO_ROOT
