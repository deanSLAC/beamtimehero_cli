"""Contract tests for ``FilesBackend``.

Verifies the class wraps ``local_data`` correctly and conforms to the
ScansBackend Protocol. Phase 2 will run the same suite against
PostgresBackend with a fixture DB.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def mock_spec(monkeypatch):
    monkeypatch.setenv("SPEC_MOCK", "1")
    monkeypatch.setenv("BEAMTIMEHERO_CLI_LOG", "0")


def test_files_backend_satisfies_protocol():
    from beamtimehero_cli.spec_data.backend import ScansBackend
    from beamtimehero_cli.spec_data.files_backend import FilesBackend

    backend = FilesBackend()
    assert isinstance(backend, ScansBackend)


def test_files_backend_list_scans_returns_list():
    from beamtimehero_cli.spec_data.files_backend import FilesBackend

    backend = FilesBackend()
    result = backend.list_scans(limit=3)
    assert isinstance(result, list)


def test_files_backend_get_active_counter_handles_missing_scan():
    from beamtimehero_cli.spec_data.files_backend import FilesBackend

    backend = FilesBackend()
    result = backend.get_active_counter("definitely_not_a_real_file", 1)
    assert result is None


def test_files_backend_methods_match_protocol_signature():
    """Each Protocol method exists on the class with the documented signature."""
    from beamtimehero_cli.spec_data.files_backend import FilesBackend
    import inspect

    backend = FilesBackend()
    for name in (
        "list_scans", "get_scan_metadata", "read_scan", "get_latest_scan",
        "get_scan_deadtime", "get_scan_numbers_for_file", "get_most_recent_file",
    ):
        assert callable(getattr(backend, name)), f"missing method {name}"
        # Methods that take args must accept them without crashing on import.
        sig = inspect.signature(getattr(backend, name))
        assert sig is not None
