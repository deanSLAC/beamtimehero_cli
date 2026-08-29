"""Merged two-column XAS ASCII — loader for already-processed spectra.

Post-processing pipelines (chemcatal's ``xas_core/specio.write_two_column_dat``,
Athena exports, hand merges) write one spectrum per file as plain two-column
ASCII: energy in eV, then an intensity (typically normalized mu). These are
NOT scan files — no reps, no counters, no headers beyond free-text comments —
so the SPEC/collector backends can't see them, yet users routinely ask to
overlay/compare them (e.g. ``MERGE/*.dat``).

This module gives them the same treatment ``ssrl_ascii.py`` gives the
collector format: a cheap sniffer plus a parser producing plain arrays.
``spec_data.scans.get_normalized_scan_arrays`` routes to it when a requested
file has no scans but IS a two-column ASCII, so every multi-scan tool accepts
merged files without touching the SPEC metadata cache.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

# Comment markers accepted in the header/body ('#' from specio/Athena, '!'
# from some beamline exporters, ';' from generic plotting tools).
_COMMENT_PREFIXES = ("#", "!", ";")

# SPEC files also open with '#' lines; these markers identify them so the
# sniffer never claims a (pathological) two-column SPEC scan.
_SPEC_MARKERS = ("#F", "#S", "#L", "#O0")

_MIN_POINTS = 5
# Plausible photon-energy window (eV): rejects k-space / R-space / pixel axes.
_ENERGY_MIN_EV = 100.0
_ENERGY_MAX_EV = 200000.0
_SNIFF_BYTES = 8192


def _split_row(line: str) -> list[str]:
    """Split one data row on commas (CSV-ish) or whitespace."""
    if "," in line:
        return [p for p in (s.strip() for s in line.split(",")) if p]
    return line.split()


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith(_COMMENT_PREFIXES)


def _energy_axis_plausible(energy: np.ndarray) -> bool:
    """Strictly monotonic (either direction) and inside the eV window."""
    if energy.size < _MIN_POINTS:
        return False
    d = np.diff(energy)
    if not (np.all(d > 0) or np.all(d < 0)):
        return False
    lo, hi = float(energy.min()), float(energy.max())
    return _ENERGY_MIN_EV <= lo and hi <= _ENERGY_MAX_EV and hi > lo


def is_twocol_ascii(path: str | Path) -> bool:
    """Cheap sniff: a 2-column numeric ASCII whose first column is energy.

    Accepts ``#`` / ``!`` / ``;`` comment headers and whitespace- or
    comma-separated rows; requires >= 5 data rows in the sniffed head, a
    strictly monotonic first column within a plausible eV range, and no
    NUL bytes. SPEC files (``#F``/``#S``/``#L`` markers, multi-column
    rows) and collector ASCII (banner row) fail the row-shape checks.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(_SNIFF_BYTES)
    except OSError:
        return False
    if not head or b"\x00" in head:
        return False
    text = head.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if len(head) == _SNIFF_BYTES and lines:
        lines = lines[:-1]  # drop the possibly-truncated tail line

    energies: list[float] = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if _is_comment(s):
            if s.split(None, 1)[0] in _SPEC_MARKERS:
                return False
            continue
        parts = _split_row(s)
        if len(parts) != 2:
            return False
        try:
            e = float(parts[0])
            float(parts[1])
        except ValueError:
            return False
        energies.append(e)

    return _energy_axis_plausible(np.asarray(energies, dtype=float))


def read_twocol(path: str | Path) -> tuple[np.ndarray, np.ndarray, dict]:
    """Parse a merged two-column ASCII into ``(energy, intensity, meta)``.

    Energy is returned ascending (descending files are flipped). ``meta``
    carries ``path``, ``n_points``, ``e_min_ev``/``e_max_ev`` and the
    stripped header ``comments``. Raises ValueError when the file does not
    hold a plausible two-column spectrum.
    """
    path = Path(path)
    comments: list[str] = []
    energy: list[float] = []
    intensity: list[float] = []
    for line in path.read_text(errors="replace").splitlines():
        s = line.strip()
        if not s:
            continue
        if _is_comment(s):
            comments.append(s.lstrip("".join(_COMMENT_PREFIXES)).strip())
            continue
        parts = _split_row(s)
        if len(parts) != 2:
            raise ValueError(f"{path}: not a two-column ASCII (row {s!r})")
        try:
            energy.append(float(parts[0]))
            intensity.append(float(parts[1]))
        except ValueError:
            raise ValueError(f"{path}: non-numeric row {s!r}") from None

    e = np.asarray(energy, dtype=float)
    i = np.asarray(intensity, dtype=float)
    if not _energy_axis_plausible(e):
        raise ValueError(
            f"{path}: first column is not a plausible monotonic energy axis "
            f"in eV ({e.size} points)."
        )
    if e.size > 1 and e[1] < e[0]:
        e, i = e[::-1].copy(), i[::-1].copy()

    meta = {
        "path": str(path),
        "n_points": int(e.size),
        "e_min_ev": float(e[0]),
        "e_max_ev": float(e[-1]),
        "comments": comments,
    }
    return e, i, meta
