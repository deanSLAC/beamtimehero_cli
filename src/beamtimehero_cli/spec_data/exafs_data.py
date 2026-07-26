"""EXAFS data loading + reduction — the exafs-branch chokepoint.

Bridges scan data to the pure math in ``analysis/exafs.py`` the way
``xrs_data.py`` does for the Raman branch: load reps on the chosen counter,
divide by I0, drop aborted sweeps, glitch-mask, merge, then hand a clean
merged mu(E) to normalization + chi extraction.

Two data sources, selected per call:

- Default: the SPEC chain (``scans.get_normalized_scan_arrays`` with
  ``normalization='divide_by_i0'`` — EXAFS extraction does its own
  pre/post-edge normalization, so the flat-anchor edge-step must NOT be
  applied here).
- ``collector_dir`` given (or ``SSRL_COLLECTOR_DIR`` set and file_name matches an
  SSRL scan group): the ``SSRLAsciiBackend``, where ``file_name`` is the
  scan-group key and scan numbers are sweep numbers. Signal counter
  defaults to ``SCA_sum`` (the summed Xspress3 fluorescence) — explicit
  ``counter`` always wins, per ``ref counter-selection``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from beamtimehero_cli.analysis import xas
from beamtimehero_cli.interpretation import quality
from beamtimehero_cli.spec_data import scans

SSRL_DEFAULT_COUNTER = "SCA_sum"


def _load_ssrl_reps(
    collector_dir: str | None,
    file_name: str | None,
    scan_numbers: list[int] | None,
    counter: str | None,
) -> tuple[pd.DataFrame, str, str, list[int]]:
    """Load SSRL sweeps as I0-divided rep columns on an aligned energy grid."""
    from beamtimehero_cli.spec_data.ssrl_backend import SSRLAsciiBackend

    backend = SSRLAsciiBackend(collector_dir)
    if file_name is None:
        file_name = backend.get_most_recent_file()
        if file_name is None:
            raise ValueError(f"No SSRL sweep files found in {backend.data_dir}.")
    sweeps = scan_numbers or backend.get_scan_numbers_for_file(file_name)
    if not sweeps:
        raise ValueError(
            f"No sweeps for SSRL scan group '{file_name}'. "
            f"Known groups: {[g['file_name'] for g in backend.list_groups()][:20]}"
        )
    counter = counter or SSRL_DEFAULT_COUNTER

    loaded: list[tuple[int, np.ndarray, np.ndarray]] = []
    for sweep in sweeps:
        df = backend.read_scan(file_name, sweep)
        if df is None or counter not in df.columns or "I0" not in df.columns:
            continue
        energy = df.index.values.astype(float)
        i0 = df["I0"].values.astype(float)
        i0_safe = np.where(i0 == 0, 1.0, i0)
        sig = df[counter].values.astype(float) / i0_safe
        loaded.append((sweep, energy, sig))
    if not loaded:
        raise ValueError(
            f"No usable sweeps on counter '{counter}' in group '{file_name}'."
        )
    # Sweeps share the requested grid but record jittered ACHIEVED energies
    # (~0.01 eV mono repeatability), so an exact/tolerance index align finds
    # no overlap. Interpolate every sweep onto the longest sweep's achieved
    # grid instead; a sweep contributes NaN outside its own range, which is
    # exactly what filter_short_reps keys on for aborted sweeps.
    ref_sweep, grid, _sig = max(loaded, key=lambda t: len(t[1]))
    columns = {}
    for sweep, energy, sig in loaded:
        columns[f"S{sweep:03d}"] = np.interp(
            grid, energy, sig, left=np.nan, right=np.nan)
    combined = pd.DataFrame(columns, index=grid)
    combined.attrs["counter"] = counter
    combined.attrs["reference_sweep"] = ref_sweep
    return combined, file_name, counter, [s for s, _e, _v in loaded]


def load_mu(
    file_name: str | None = None,
    scan_numbers: list[int] | None = None,
    counter: str | None = None,
    collector_dir: str | None = None,
    source: str | None = None,
    mask_glitches: bool = True,
) -> dict:
    """Load, filter, and merge reps into one mu(E) for EXAFS extraction.

    Returns a dict with ``energy``, ``mu`` (rep mean, I0-divided, un-
    normalized), ``reps`` (n_scans × n_points), plus provenance: source,
    file_name, counter, scan_numbers used, dropped short reps, glitch count.
    Raises ValueError on any data problem (one shared error path for the
    tool handlers).
    """
    use_ssrl = source == "collector" or collector_dir is not None
    dropped: list[str] = []
    counter_warning = None

    if use_ssrl:
        combined, file_name, counter, used = _load_ssrl_reps(
            collector_dir, file_name, scan_numbers, counter)
        src = "ssrl_ascii"
    else:
        combined, file_name, counter, used = scans.get_normalized_scan_arrays(
            file_name, scan_numbers=scan_numbers, counter=counter,
            normalization="divide_by_i0",
        )
        counter_warning = combined.attrs.get("counter_warning")
        src = "spec"

    combined, dropped = xas.filter_short_reps(combined)
    combined = combined.dropna()
    if combined.empty or len(combined) < 20:
        raise ValueError(
            f"Too few overlapping energy points across the selected reps "
            f"({len(combined)}) for EXAFS extraction."
        )

    energy = combined.index.values.astype(float)
    reps = combined.values.T  # (n_scans, n_points)
    mu = reps.mean(axis=0)

    n_glitch = 0
    if mask_glitches:
        mask = quality.detect_glitches(energy, mu)
        n_glitch = int(mask.sum())
        if n_glitch:
            mu = quality.interpolate_over_mask(energy, mu, mask)

    return {
        "energy": energy,
        "mu": mu,
        "reps": reps,
        "source": src,
        "file_name": file_name,
        "counter": counter,
        "counter_warning": counter_warning,
        "scan_numbers": used,
        "n_reps": reps.shape[0],
        "dropped_short_reps": dropped,
        "n_glitch_points": n_glitch,
    }
