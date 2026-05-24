"""Backend abstraction for scan data.

Each deployment supplies a backend implementing this Protocol:

- ``FilesBackend`` (in ``files_backend.py``) walks SPEC files on disk
  and keeps a JSON metadata cache. Used by beamline-local apps.
- ``PostgresBackend`` (added in Phase 2) reads metadata from the
  ``BL15-2_scan_metadata`` table and scan DataFrames from a pickle dir.
  Used by S3DF/playground.

Tool implementations call into ``backend.<method>(...)`` and do not care
which one is wired up.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class ScansBackend(Protocol):
    """Core scan-data operations every backend must support."""

    def list_scans(self, limit: int = 20) -> list[dict]:
        """Return scans most-recent first.

        Each dict has at least: ``file_name``, ``scan_number``,
        ``scan_command``, ``date_time``, ``num_points``. Other keys
        (counters, count_time, acquisition_seconds) are best-effort.
        """
        ...

    def get_scan_metadata(self, file_name: str, scan_number: int) -> dict | None:
        """Full metadata for one scan. Returns None if not found."""
        ...

    def read_scan(self, file_name: str, scan_number: int) -> pd.DataFrame | None:
        """Scan data as a DataFrame.

        Index = scanned motor; columns = counters. ``df.attrs`` carries
        ``count_time``, ``motor_positions``, ``scan_command``,
        ``date_time``, and ``counter_names``. Returns None if the scan
        cannot be located.
        """
        ...

    def get_latest_scan(self) -> dict | None:
        """Metadata for the most recent scan across all files."""
        ...

    def get_scan_deadtime(self, file_name: str, scan_number: int) -> dict | None:
        """Wall-clock vs acquisition time + dead-time fraction. None if absent."""
        ...

    def get_scan_numbers_for_file(self, file_name: str) -> list[int]:
        """Scan numbers present for ``file_name``, in scan order."""
        ...

    def get_most_recent_file(self) -> str | None:
        """File name of the most-recent SPEC file (None if none exist)."""
        ...


# Optional-capability methods that some backends provide:
#
# - get_experiment_context(*, hours, file_name) -> dict
# - get_sample_coverage_report(*, hours, file_name) -> dict
# - get_beam_stability(*, hours) -> dict
# - get_activity_summary(*, hours) -> dict
#
# Tools that need these probe with ``hasattr(backend, "<name>")``. Phase
# 2 adds them to PostgresBackend; FilesBackend may or may not implement
# them, depending on what's computable from SPEC files alone.
