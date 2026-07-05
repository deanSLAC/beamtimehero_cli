"""XRS data loading + reduction over the file/DB backends.

Bridges the raw SPEC scans (via ``scans``) to the pure math in
``analysis/xrs.py``: load reps on the chosen counter, divide by I0, convert to
the energy-loss axis using an elastic-line calibration, align, and average.

Also owns the session **elastic-line calibration store** (a JSON record of the
ω=0 anchor and instrumental resolution per file), mirroring the XAS
``interpretation.calibration_store`` pattern — but for XRS this is a processing
prerequisite, not an interpretation gate: without an elastic reference the loss
axis is only pinned to the mono energy, not to true energy transfer.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np

from beamtimehero_cli import config as bl_config
from beamtimehero_cli.analysis import xas, xrs
from beamtimehero_cli.spec_data import scans

ELASTIC_FILENAME = "beamtimehero_xrs_elastic.json"


# ---------------------------------------------------------------------------
# Elastic-line calibration store
# ---------------------------------------------------------------------------

def _store_path() -> Path:
    return Path(bl_config.BL_SCAN_DIR) / ELASTIC_FILENAME


def load_elastic_records() -> list[dict]:
    path = _store_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return data.get("records", []) if isinstance(data, dict) else []


def record_elastic(
    file_name: str, scan_number: int, counter: str,
    elastic_center_ev: float, resolution_fwhm_ev: float | None, method: str,
    notes: str = "",
) -> dict:
    """Append one elastic-line calibration record and return it."""
    record = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "file_name": file_name,
        "scan_number": scan_number,
        "counter": counter,
        "elastic_center_ev": float(elastic_center_ev),
        "resolution_fwhm_ev": (
            float(resolution_fwhm_ev) if resolution_fwhm_ev is not None else None
        ),
        "method": method,
        "notes": notes,
    }
    records = load_elastic_records()
    records.append(record)
    # Best-effort persist: chemcatal mounts the scan dir read-only, so a write
    # failure must not break the (read-only-valuable) calibration itself.
    try:
        _store_path().write_text(json.dumps({"records": records}, indent=2))
        record["persisted"] = True
    except OSError:
        record["persisted"] = False
    return record


def current_elastic(file_name: str | None = None) -> dict | None:
    """Most recent elastic calibration, optionally filtered to one file."""
    records = load_elastic_records()
    if file_name is not None:
        records = [r for r in records if r.get("file_name") == file_name]
    return records[-1] if records else None


def _resolve_elastic_center(file_name, elastic_center_ev):
    """Return (center or None, source-string)."""
    if elastic_center_ev is not None:
        return float(elastic_center_ev), "caller-specified"
    rec = current_elastic(file_name) or current_elastic(None)
    if rec is not None:
        return rec["elastic_center_ev"], (
            f"stored calibration (scan {rec.get('scan_number')}, "
            f"{rec.get('timestamp')})"
        )
    return None, "none — loss axis is mono energy, not calibrated energy transfer"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_scan_signal(file_name, scan_number, counter, normalize_by="I0"):
    """One scan → (energy, signal/normalize_by). Raises on missing counter."""
    df = scans.read_processed_scan(file_name, scan_number)
    if df is None:
        raise ValueError(f"Scan not found: {file_name} #{scan_number}")
    if counter not in df.columns:
        raise ValueError(
            f"Counter '{counter}' not in scan {scan_number}; available: {list(df.columns)}"
        )
    energy = df.index.values.astype(float)
    signal = df[counter].values.astype(float)
    if normalize_by and normalize_by in df.columns:
        i0 = df[normalize_by].values.astype(float)
        signal = signal / np.where(i0 == 0, 1.0, i0)
    return energy, signal


def _resolve_counter(file_name, scan_number, counter):
    """(counter, warning) — auto-pick + flat-channel guardrail when counter=None."""
    if counter is not None:
        return counter, None
    df = scans.read_processed_scan(file_name, scan_number)
    if df is None:
        raise ValueError(f"Scan not found: {file_name} #{scan_number}")
    picked, _reason = xas.pick_active_counter(df)
    return picked, xas.counter_selection_warning(df, picked)


def calibrate_energy_loss(file_name, scan_number, counter=None, normalize_by="I0"):
    """Fit the elastic line of one scan and record the calibration.

    Returns the fit dict plus the stored record. ``scan_number`` should be an
    elastic scan (``ascan mono`` with the analyzer fixed).
    """
    counter, warning = _resolve_counter(file_name, scan_number, counter)
    energy, signal = load_scan_signal(file_name, scan_number, counter, normalize_by)
    fit = xrs.fit_elastic_line(energy, signal)
    record = record_elastic(
        file_name, scan_number, counter,
        fit["elastic_center_ev"], fit.get("resolution_fwhm_ev"), fit["method"],
    )
    out = {**fit, "file_name": file_name, "scan_number": scan_number,
           "counter": counter, "record": record}
    if warning:
        out["counter_warning"] = warning
    return out


def reduce_xrs(
    file_name=None, counter=None, scan_numbers=None, elastic_center_ev=None,
    normalize_by="I0",
):
    """Average XRS reps onto a common energy-loss grid.

    Loads each rep on ``counter`` (auto-picked + warned if None), divides by I0,
    converts to the loss axis via the resolved elastic center, and averages with
    ``analysis.xrs.align_and_average``. Returns a dict with numpy arrays
    ``loss/mean/sem/std`` plus context (counter, elastic center + source,
    counter_warning). Raises ValueError on no usable scans.
    """
    if file_name is None:
        file_name = scans.get_most_recent_file()
        if file_name is None:
            raise ValueError("No SPEC files found.")
    if scan_numbers is None:
        from beamtimehero_cli.spec_data import local_data
        scan_numbers = local_data.get_scan_numbers_for_file(file_name)
    if not scan_numbers:
        raise ValueError(f"No scans found for file '{file_name}'.")

    counter, warning = _resolve_counter(file_name, scan_numbers[0], counter)
    center, center_source = _resolve_elastic_center(file_name, elastic_center_ev)

    loss_list, inten_list, used = [], [], []
    for sn in scan_numbers:
        try:
            energy, signal = load_scan_signal(file_name, sn, counter, normalize_by)
        except ValueError:
            continue
        loss = xrs.to_energy_loss(energy, center) if center is not None else energy
        loss_list.append(loss)
        inten_list.append(signal)
        used.append(sn)

    if not loss_list:
        raise ValueError(
            f"No scans with counter '{counter}' found in '{file_name}'."
        )
    avg = xrs.align_and_average(loss_list, inten_list)
    avg.update({
        "file_name": file_name,
        "counter": counter,
        "scan_numbers": used,
        "elastic_center_ev": center,
        "elastic_center_source": center_source,
        "counter_warning": warning,
        "axis": "energy_loss_ev" if center is not None else "mono_energy_ev",
    })
    return avg
