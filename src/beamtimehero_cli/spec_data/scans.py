"""Scan data operations -- reads SPEC files directly via silx.

Uses local_data module for metadata queries and scan reading.
No pickle files required.

Pure-math helpers (edge-step normalization, active-counter selection,
per-rep noise estimation, averaging) live in ``beamtimehero_cli.analysis.xas``
so the postgres-backed flow can reuse them without copy-pasting.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

from beamtimehero_cli.analysis import xas
from beamtimehero_cli.spec_data import local_data


def list_processed_scans(limit=20):
    """List scans, most recent first."""
    return local_data.list_processed_scans(limit=limit)


def get_scan_metadata(file_name, scan_number):
    """Get full metadata for a single scan."""
    return local_data.get_scan_metadata(file_name, scan_number)


def read_processed_scan(file_name, scan_number):
    """Read scan data from the SPEC file. Returns DataFrame or None."""
    return local_data.read_processed_scan(file_name, scan_number)


def get_scan_deadtime(file_name, scan_number):
    """Get dead time info for a single scan."""
    return local_data.get_scan_deadtime(file_name, scan_number)


def get_active_counter(file_name, scan_number):
    """Determine the 'active' fluorescence/absorption counter for a scan.

    Selection logic lives in ``analysis.xas.pick_active_counter`` and is
    shared with the postgres backend.
    """
    df = read_processed_scan(file_name, scan_number)
    if df is None:
        return None
    counter, reason = xas.pick_active_counter(df)
    return {
        "file_name": file_name,
        "scan_number": scan_number,
        "active_counter": counter,
        "reason": reason,
    }


# Backward-compat shim: re-export the pure math from the analysis layer
# so callers that still import ``scans._edge_step_normalize`` keep working.
_edge_step_normalize = xas.edge_step_normalize


def edge_step_normalize_scan(file_name, scan_number, counter=None, normalize_by="I0"):
    """Load a scan, normalize by I0, then apply edge-step normalization."""
    df = read_processed_scan(file_name, scan_number)
    if df is None:
        return None

    if counter is None:
        active = get_active_counter(file_name, scan_number)
        if active is None:
            return None
        counter = active["active_counter"]

    try:
        energy, normalized = _edge_step_normalize(df, counter, normalize_by)
    except KeyError as e:
        return {"error": str(e)}

    result_df = pd.DataFrame({"energy": energy, "normalized": normalized})
    result_df = result_df.set_index("energy")

    return {
        "file_name": file_name,
        "scan_number": scan_number,
        "counter": counter,
        "normalize_by": normalize_by,
        "num_points": len(result_df),
        "data": result_df.to_string(),
    }


def get_most_recent_file():
    """Find the most recently modified SPEC file (excluding alignment)."""
    return local_data.get_most_recent_file()


# Energy-grid alignment tolerance: 4 decimals of eV (0.1 meV) — far below
# any mono step size, far above float jitter between nominally-equal grids.
_ENERGY_ALIGN_DECIMALS = 4


def _concat_aligned(series_list, decimals=_ENERGY_ALIGN_DECIMALS):
    """Concat per-scan Series on a tolerance-aligned energy index.

    Exact-float index alignment in ``pd.concat`` silently fans out rows
    (and later ``dropna()`` discards them) when energy grids carry float
    jitter between reps. When the grids are already exactly identical
    the series are concatenated as-is — behavior (and index values) are
    unchanged. Otherwise each index is rounded to ``decimals`` decimals
    of eV before concat; duplicate rounded energies within one scan are
    averaged.
    """
    if len(series_list) > 1:
        first = series_list[0].index
        identical = all(
            len(s.index) == len(first) and np.array_equal(s.index.values, first.values)
            for s in series_list[1:]
        )
        if not identical:
            aligned = []
            for s in series_list:
                s2 = s.copy()
                s2.index = np.round(s2.index.values.astype(float), decimals)
                if s2.index.has_duplicates:
                    s2 = s2.groupby(level=0).mean()
                    s2.name = s.name
                aligned.append(s2)
            series_list = aligned
    return pd.concat(series_list, axis=1)


def get_normalized_scan_arrays(file_name=None, e_min=None, e_max=None, scan_numbers=None):
    """Load all scans for a file, normalize, and return as a DataFrame on a common energy grid.

    Parameters
    ----------
    file_name : str, optional
        SPEC file name. If None, uses the most recent file.
    e_min, e_max : float, optional
        If both are given, restrict the returned DataFrame to rows whose energy
        index is in [e_min, e_max]. Edge-step normalization is still performed
        on the full scan (so pre/post anchors are unchanged) — only the
        returned slice is windowed.
    scan_numbers : list[int], optional
        If given, restrict to these specific scan numbers (used by per-spot
        analysis to run the same pipeline on a subset).
    """
    if file_name is None:
        file_name = get_most_recent_file()
        if file_name is None:
            raise ValueError("No SPEC files found.")

    if scan_numbers is None:
        scan_numbers = local_data.get_scan_numbers_for_file(file_name)

    if not scan_numbers:
        raise ValueError(f"No scans found for file '{file_name}'.")

    active = get_active_counter(file_name, scan_numbers[0])
    if active is None:
        raise ValueError(f"Could not load scan data for '{file_name}' scan {scan_numbers[0]}.")
    counter = active["active_counter"]

    normalized_scans = []
    used_scans = []
    for sn in scan_numbers:
        df = read_processed_scan(file_name, sn)
        if df is None:
            continue
        try:
            energy, norm = _edge_step_normalize(df, counter, normalize_by="I0")
        except KeyError:
            continue
        normalized_scans.append(pd.Series(norm, index=energy, name=f"S{sn:03d}"))
        used_scans.append(sn)

    if not normalized_scans:
        raise ValueError(f"No valid scans to normalize in '{file_name}'.")

    combined = _concat_aligned(normalized_scans)

    if e_min is not None and e_max is not None:
        if e_min >= e_max:
            raise ValueError(f"e_min ({e_min}) must be less than e_max ({e_max}).")
        windowed = combined.loc[(combined.index >= e_min) & (combined.index <= e_max)]
        if len(windowed) < 5:
            raise ValueError(
                f"Energy window [{e_min}, {e_max}] yielded only {len(windowed)} points. "
                f"Available range: [{combined.index.min():.2f}, {combined.index.max():.2f}]."
            )
        combined = windowed

    return combined, file_name, counter, used_scans


# Backward-compat shim — implementation lives in ``analysis.xas``.
_estimate_per_rep_noise = xas.estimate_per_rep_noise


def average_energy_scans_arrays(
    file_name=None,
    e_min=None,
    e_max=None,
    weighting: str = "equal",
    scan_numbers=None,
):
    """Array-returning core of :func:`average_energy_scans`.

    Returns ``(info, result_df)`` where ``info`` is the summary dict
    WITHOUT the rendered ``"data"`` string and ``result_df`` is the
    averaged DataFrame (index=energy, columns=``average``, ``std``).
    On failure returns ``({"error": ...}, None)``.

    Use this from numeric consumers (plotting, analysis) — the
    ``to_string()`` rendering in :func:`average_energy_scans` exists
    only for LLM-facing tool output.
    """
    try:
        combined, file_name, counter, used_scans = get_normalized_scan_arrays(
            file_name, e_min=e_min, e_max=e_max, scan_numbers=scan_numbers
        )
    except ValueError as e:
        return {"error": str(e)}, None

    if weighting == "inverse_variance":
        # For weighting we need a baseline estimate from the FULL scan, not the
        # windowed slice (the slice may not include the baseline).
        full_combined, _, _, _ = get_normalized_scan_arrays(
            file_name, scan_numbers=scan_numbers
        )
        sigmas = _estimate_per_rep_noise(full_combined)
        weights = 1.0 / np.square(sigmas)
        weights = weights / weights.sum()
        avg = (combined.values * weights[np.newaxis, :]).sum(axis=1)
        # Weighted std across reps (using the same weights, ddof~0)
        diff = combined.values - avg[:, np.newaxis]
        var = (np.square(diff) * weights[np.newaxis, :]).sum(axis=1)
        std = np.sqrt(var)
        avg = pd.Series(avg, index=combined.index)
        std = pd.Series(std, index=combined.index)
        weights_used = weights.tolist()
    elif weighting == "equal":
        avg = combined.mean(axis=1)
        std = combined.std(axis=1)
        weights_used = None
    else:
        return {"error": f"Unknown weighting '{weighting}'. Use 'equal' or 'inverse_variance'."}, None

    result_df = pd.DataFrame({"energy": avg.index, "average": avg.values, "std": std.values})
    result_df = result_df.set_index("energy")

    info = {
        "file_name": file_name,
        "active_counter": counter,
        "num_scans_averaged": len(used_scans),
        "scan_numbers": used_scans,
        "num_points": len(result_df),
        "weighting": weighting,
        "energy_window": [e_min, e_max] if (e_min is not None and e_max is not None) else None,
    }
    if weights_used is not None:
        info["weights_used"] = [round(w, 6) for w in weights_used]
    return info, result_df


def average_energy_scans(
    file_name=None,
    e_min=None,
    e_max=None,
    weighting: str = "equal",
    scan_numbers=None,
):
    """Average all energy scans in a SPEC file after edge-step normalization.

    Parameters
    ----------
    file_name : str, optional
        SPEC file name. If None, uses the most recent file.
    e_min, e_max : float, optional
        Restrict the returned average to this energy window. Normalization is
        still done on the full scan; only the output is windowed.
    weighting : {"equal", "inverse_variance"}, default "equal"
        "equal": unweighted mean across scans.
        "inverse_variance": weight each scan by 1/sigma_i^2 where sigma_i is
        estimated from the post-edge baseline std of that scan. Higher-SNR
        spots contribute more.
    scan_numbers : list[int], optional
        If given, restrict to these specific scan numbers.

    The returned dict carries the averaged data rendered via ``to_string``
    under ``"data"`` (LLM-facing). Numeric consumers should call
    :func:`average_energy_scans_arrays` instead of re-parsing that text.
    """
    info, result_df = average_energy_scans_arrays(
        file_name=file_name, e_min=e_min, e_max=e_max,
        weighting=weighting, scan_numbers=scan_numbers,
    )
    if result_df is None:
        return info
    out = {k: v for k, v in info.items() if k != "weights_used"}
    out["data"] = result_df.to_string()
    if "weights_used" in info:
        out["weights_used"] = info["weights_used"]
    return out


def average_latest_energy_scans(e_min=None, e_max=None, weighting: str = "equal"):
    """Find the latest file with >1 energy-motor scan and return the average."""
    file_name = local_data.average_latest_energy_scans_file()
    if not file_name:
        return {"error": "No file found with more than 1 energy scan."}
    return average_energy_scans(file_name=file_name, e_min=e_min, e_max=e_max, weighting=weighting)


def group_scans_by_spot(file_name, tol_mm: float = 0.05):
    """Group a file's scans by sample spot, using motor positions (Sx, Sy, Sz).

    Two scans are considered the same spot if their Sx, Sy, Sz all agree within
    `tol_mm`. Returns a list of {"spot_id": int, "center": {Sx,Sy,Sz},
    "scan_numbers": [...]} entries, ordered by first-appearance.

    Reads motor_positions from each scan's df.attrs. Scans missing Sx/Sy/Sz are
    grouped under spot_id=-1 (unknown).
    """
    scan_numbers = local_data.get_scan_numbers_for_file(file_name)
    if not scan_numbers:
        return {"error": f"No scans found for file '{file_name}'."}

    def _motor_xyz(motors: dict) -> tuple[float, float, float] | None:
        """Pull (Sx, Sy, Sz) from motor_positions, tolerating the silx quirk
        where single-space-separated motor names get returned as one joined
        key. We re-split the joined key and pair with the scan's own #P0
        positions stored on disk if needed.
        """
        if not motors:
            return None
        # Direct lookup — works when names parsed correctly.
        try:
            return float(motors["Sx"]), float(motors["Sy"]), float(motors["Sz"])
        except (KeyError, TypeError, ValueError):
            pass
        # Fallback: silx joined the motor names. Each key is a long string;
        # the corresponding value is just the FIRST motor's position. We
        # cannot recover Sx/Sy/Sz from this dict alone — pass through.
        return None

    def _motor_xyz_from_p0(file_name: str, sn: int) -> tuple[float, float, float] | None:
        """Last-resort: parse the #P0 / #O0 lines from the raw SPEC file."""
        from beamtimehero_cli.spec_data import local_data as _ld
        cache = _ld._load_cache()
        entry = cache.get(f"{file_name}::{sn}")
        if not entry or not entry.get("file_path"):
            return None
        try:
            from pathlib import Path as _P
            text = _P(entry["file_path"]).read_text(errors="ignore")
        except OSError:
            return None
        # Find the file-level #O0 (first one) and the per-scan #P0.
        names: list[str] = []
        for line in text.splitlines():
            if line.startswith("#O0 "):
                names = line[4:].split()
                break
        if not names:
            return None
        # Now find the scan's own #P0
        in_scan = False
        for line in text.splitlines():
            if line.startswith(f"#S {sn} "):
                in_scan = True
                continue
            if in_scan and line.startswith("#S "):
                break
            if in_scan and line.startswith("#P0 "):
                try:
                    vals = [float(x) for x in line[4:].split()]
                except ValueError:
                    return None
                idx = {n: i for i, n in enumerate(names)}
                if "Sx" in idx and "Sy" in idx and "Sz" in idx:
                    try:
                        return vals[idx["Sx"]], vals[idx["Sy"]], vals[idx["Sz"]]
                    except IndexError:
                        return None
                return None
        return None

    spots = []  # list of dicts: {"center": (Sx, Sy, Sz), "scan_numbers": [...]}
    unknown = []

    for sn in scan_numbers:
        df = read_processed_scan(file_name, sn)
        if df is None or not hasattr(df, "attrs"):
            unknown.append(sn)
            continue
        motors = df.attrs.get("motor_positions") or {}
        xyz = _motor_xyz(motors) or _motor_xyz_from_p0(file_name, sn)
        if xyz is None:
            unknown.append(sn)
            continue
        sx, sy, sz = xyz

        matched = False
        for spot in spots:
            cx, cy, cz = spot["center"]
            if abs(cx - sx) <= tol_mm and abs(cy - sy) <= tol_mm and abs(cz - sz) <= tol_mm:
                spot["scan_numbers"].append(sn)
                matched = True
                break
        if not matched:
            spots.append({"center": (sx, sy, sz), "scan_numbers": [sn]})

    out = []
    for i, spot in enumerate(spots):
        cx, cy, cz = spot["center"]
        out.append({
            "spot_id": i,
            "center": {"Sx": round(cx, 4), "Sy": round(cy, 4), "Sz": round(cz, 4)},
            "scan_numbers": spot["scan_numbers"],
            "n_scans": len(spot["scan_numbers"]),
        })

    if unknown:
        out.append({"spot_id": -1, "center": None, "scan_numbers": unknown, "n_scans": len(unknown)})

    return {
        "file_name": file_name,
        "tol_mm": tol_mm,
        "n_spots": len([s for s in out if s["spot_id"] != -1]),
        "spots": out,
    }


def get_raw_counter_arrays(file_name=None, scan_numbers=None):
    """Load raw active-counter arrays per scan (NOT normalized), aligned on a
    common energy grid. Used for counts-based Poisson floor calculations.

    Returns (combined_counts_df, file_name, counter, used_scans). The DataFrame
    holds the active counter divided by count time (rate, in counts/sec) so
    different scans with different count times are comparable in shape; total
    counts per point per scan = rate * count_time, exposed in attrs.
    """
    if file_name is None:
        file_name = get_most_recent_file()
        if file_name is None:
            raise ValueError("No SPEC files found.")
    if scan_numbers is None:
        scan_numbers = local_data.get_scan_numbers_for_file(file_name)
    if not scan_numbers:
        raise ValueError(f"No scans found for file '{file_name}'.")

    active = get_active_counter(file_name, scan_numbers[0])
    if active is None:
        raise ValueError(f"Could not load scan data for '{file_name}' scan {scan_numbers[0]}.")
    counter = active["active_counter"]

    series_list = []
    used = []
    count_times = []
    for sn in scan_numbers:
        df = read_processed_scan(file_name, sn)
        if df is None or counter not in df.columns:
            continue
        energy = df.index.values.astype(float)
        ct = df.attrs.get("count_time") or 1.0
        rate = df[counter].values.astype(float) / float(ct)
        series_list.append(pd.Series(rate, index=energy, name=f"S{sn:03d}"))
        used.append(sn)
        count_times.append(float(ct))

    if not series_list:
        raise ValueError(f"No scans with counter '{counter}' found in '{file_name}'.")

    combined = _concat_aligned(series_list)
    combined.attrs["count_times"] = count_times
    combined.attrs["counter"] = counter
    return combined, file_name, counter, used
