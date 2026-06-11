"""Global pytest fixtures for Sentinel tests.

The most important fixture here is `isolate_data_dir` (autouse=True): every test
function gets its own throwaway SENTINEL_DATA_DIR so no test ever writes to the real
data/ directory.  Tests that need a specific path can still call
`monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))` — that overrides this
fixture's value for that test only.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SENTINEL_DISABLE_AUTH", "1")
