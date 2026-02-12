"""Shared fixtures and markers for gpx2fab tests."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests that run the full pipeline (deselect with '-m \"not slow\"')")


@pytest.fixture(scope="session")
def repo_root():
    return REPO_ROOT


@pytest.fixture(scope="session")
def cache_dir(repo_root):
    return repo_root / ".cache"


@pytest.fixture(scope="session")
def hungarian_gpx_bytes(repo_root):
    return (repo_root / "hungarian-blue-trail" / "input" / "okt_teljes_20260130.gpx").read_bytes()


@pytest.fixture(scope="session")
def hungarian_output_dir(repo_root):
    return repo_root / "hungarian-blue-trail" / "output"
