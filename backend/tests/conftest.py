"""Shared pytest fixtures. Every test in this folder gets its own fresh,
temporary SQLite database file - never the real backend/data/prepai.db -
so running the test suite can never add, change, or delete real interview
data on a developer's machine."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


import pytest


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test-prepai.db"))
    yield
