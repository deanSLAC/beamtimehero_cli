"""SPEC-file + JSON-cache backend.

Thin class wrapper around ``local_data`` that conforms to the
:class:`~beamtimehero_cli.spec_data.backend.ScansBackend` Protocol.
Phase 1 keeps ``local_data`` as the implementation; Phase 2 may fold the
module contents in here once everything routes through the class.
"""
from __future__ import annotations

import pandas as pd

from beamtimehero_cli.analysis import xas
from beamtimehero_cli.spec_data import local_data


class FilesBackend:
    """Reads scan data directly from SPEC files under ``BL_SCAN_DIR``.

    Maintains a JSON metadata cache at ``<BL_SCAN_DIR>/.scan_metadata_cache.json``
    so subsequent calls don't re-parse unchanged files.
    """

    # --- ScansBackend Protocol methods -------------------------------------

    def list_scans(self, limit: int = 20) -> list[dict]:
        return local_data.list_processed_scans(limit=limit)

    def get_scan_metadata(self, file_name: str, scan_number: int) -> dict | None:
        return local_data.get_scan_metadata(file_name, scan_number)

    def read_scan(self, file_name: str, scan_number: int) -> pd.DataFrame | None:
        return local_data.read_processed_scan(file_name, scan_number)

    def get_latest_scan(self) -> dict | None:
        scans = local_data.list_processed_scans(limit=1)
        return scans[0] if scans else None

    def get_scan_deadtime(self, file_name: str, scan_number: int) -> dict | None:
        return local_data.get_scan_deadtime(file_name, scan_number)

    def get_scan_numbers_for_file(self, file_name: str) -> list[int]:
        return local_data.get_scan_numbers_for_file(file_name)

    def get_most_recent_file(self) -> str | None:
        return local_data.get_most_recent_file()

    # --- Convenience that builds on the Protocol methods -------------------

    def get_active_counter(self, file_name: str, scan_number: int) -> dict | None:
        """Active counter for one scan. Delegates the column-inspection logic
        to ``analysis.xas.pick_active_counter`` so file and Postgres backends
        agree on which counter wins."""
        df = self.read_scan(file_name, scan_number)
        if df is None:
            return None
        counter, reason = xas.pick_active_counter(df)
        return {
            "file_name": file_name,
            "scan_number": scan_number,
            "active_counter": counter,
            "reason": reason,
        }
