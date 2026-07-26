"""SSRL ASCII backend — ``ScansBackend`` over EXAFS Data Collector files.

Third backend implementation alongside ``FilesBackend`` (SPEC files) and
``PostgresBackend`` (S3DF metadata DB). It maps the SSRL sweep-file
convention onto the backend addressing scheme:

    file_name   = scan group key  ("07_MOFCoTHT_..._023" — sample stem + scan no)
    scan_number = sweep number    (the MMM in "_A.MMM")

so "average scans 1..N of file X" means "merge the N sweeps of scan group X",
which is exactly the SSRL repeat-sweep semantics.

The data directory comes from the ``SSRL_DATA_DIR`` environment variable or
an explicit ``data_dir`` argument. Groups are re-scanned per call (the
directories are small, hundreds of files); no sidecar cache is kept.

Deadtime semantics differ from SPEC: an SSRL sweep records per-point
integration (real time clock) but no wall-clock column, so
``get_scan_deadtime`` reports acquisition seconds with ``dead_time_seconds``
None rather than inventing one. Detector-level deadtime lives in the
SCA/ICR columns (see ``analysis.xas.deadtime_correct``).
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from beamtimehero_cli.spec_data import ssrl_ascii

SSRL_DATA_DIR_ENV = "SSRL_DATA_DIR"


def _resolve_dir(data_dir: str | Path | None) -> Path:
    d = data_dir or os.getenv(SSRL_DATA_DIR_ENV)
    if not d:
        raise ValueError(
            "No SSRL data directory: pass data_dir or set the "
            f"{SSRL_DATA_DIR_ENV} environment variable."
        )
    path = Path(d)
    if not path.is_dir():
        raise ValueError(f"SSRL data directory does not exist: {path}")
    return path


class SSRLAsciiBackend:
    """Scan-data backend over one SSRL EXAFS Data Collector directory."""

    def __init__(self, data_dir: str | Path | None = None,
                 include_align: bool = False) -> None:
        self.data_dir = _resolve_dir(data_dir)
        self.include_align = include_align

    # -- internal ---------------------------------------------------------
    def _groups(self) -> dict[str, list[Path]]:
        return ssrl_ascii.group_sweeps(self.data_dir, include_align=self.include_align)

    def _sweep_path(self, file_name: str, scan_number: int) -> Path | None:
        for p in self._groups().get(file_name, []):
            info = ssrl_ascii.parse_sweep_name(p.name)
            if info and info["sweep"] == scan_number:
                return p
        return None

    @staticmethod
    def _meta_from(df: pd.DataFrame, file_name: str, scan_number: int) -> dict:
        a = df.attrs
        return {
            "file_name": file_name,
            "scan_number": scan_number,
            "scan_command": a.get("scan_command"),
            "date_time": a.get("date_time"),
            "num_points": a.get("num_points"),
            "counters": a.get("counters"),
            "count_time": a.get("count_time"),
            "is_complete": a.get("is_complete"),
            "region_file": a.get("region_file"),
            "detector_file": a.get("detector_file"),
            "comments": a.get("comments"),
        }

    # -- ScansBackend protocol ---------------------------------------------
    def list_scans(self, limit: int = 20) -> list[dict]:
        """Sweeps most-recent first (by file mtime), one dict per sweep."""
        entries: list[tuple[float, str, int, Path]] = []
        for key, paths in self._groups().items():
            for p in paths:
                info = ssrl_ascii.parse_sweep_name(p.name)
                if info:
                    entries.append((p.stat().st_mtime, key, info["sweep"], p))
        entries.sort(key=lambda t: t[0], reverse=True)
        out = []
        for _mtime, key, sweep, p in entries[:limit]:
            try:
                df = ssrl_ascii.read_ssrl_scan(p)
            except ValueError:
                continue
            out.append(self._meta_from(df, key, sweep))
        return out

    def get_scan_metadata(self, file_name: str, scan_number: int) -> dict | None:
        p = self._sweep_path(file_name, scan_number)
        if p is None:
            return None
        try:
            df = ssrl_ascii.read_ssrl_scan(p)
        except ValueError:
            return None
        return self._meta_from(df, file_name, scan_number)

    def read_scan(self, file_name: str, scan_number: int) -> pd.DataFrame | None:
        p = self._sweep_path(file_name, scan_number)
        if p is None:
            return None
        try:
            return ssrl_ascii.read_ssrl_scan(p)
        except ValueError:
            return None

    def get_latest_scan(self) -> dict | None:
        scans = self.list_scans(limit=1)
        return scans[0] if scans else None

    def get_scan_deadtime(self, file_name: str, scan_number: int) -> dict | None:
        p = self._sweep_path(file_name, scan_number)
        if p is None:
            return None
        try:
            df = ssrl_ascii.read_ssrl_scan(p)
        except ValueError:
            return None
        ct = df.attrs.get("count_time")
        acq = ct * len(df) if ct is not None else None
        return {
            "file_name": file_name,
            "scan_number": scan_number,
            "scan_command": df.attrs.get("scan_command"),
            "num_points": len(df),
            "count_time": ct,
            "acquisition_seconds": acq,
            "wall_clock_seconds": None,
            "dead_time_seconds": None,
            "dead_time_pct": None,
            "note": (
                "SSRL ASCII sweeps record no wall-clock column; scan-overhead "
                "deadtime is unavailable. Detector deadtime is per-element "
                "(SCA/ICR columns; see analysis.xas.deadtime_correct)."
            ),
        }

    def get_scan_numbers_for_file(self, file_name: str) -> list[int]:
        sweeps = []
        for p in self._groups().get(file_name, []):
            info = ssrl_ascii.parse_sweep_name(p.name)
            if info:
                sweeps.append(info["sweep"])
        return sorted(sweeps)

    def get_most_recent_file(self) -> str | None:
        latest = self.get_latest_scan()
        return latest["file_name"] if latest else None

    # -- convenience beyond the protocol ------------------------------------
    def list_groups(self) -> list[dict]:
        """One row per scan group: key, sweep count, sweep numbers."""
        out = []
        for key, paths in sorted(self._groups().items()):
            sweeps = sorted(
                info["sweep"] for info in map(ssrl_ascii.parse_sweep_name,
                                              (p.name for p in paths)) if info
            )
            out.append({"file_name": key, "n_sweeps": len(sweeps), "sweeps": sweeps})
        return out
