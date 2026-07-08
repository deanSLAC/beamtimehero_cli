"""Session energy-calibration record.

The one place in ``interpretation/`` that touches the filesystem: a JSON
record in the scan directory documenting how the mono energy axis maps to
a chosen reference convention (a measured foil/compound scan with a cited
assigned E0).

Per instrument spec the monochromator is calibrated against a reference
foil at the start of every beamtime and set to match it, so absolute
energy is accurate to ~0.1-0.2 eV for the whole run; mono step-loss drift
is of the same magnitude and is compensated by plotting against ``absev``
(the mono encoder). The ABSENCE of a stored record therefore does NOT make
the axis unusable: ``current_calibration`` returns an assume-calibrated
result (edges taken to sit at their tabulated positions, ~0.2 eV
systematic). An explicit recorded calibration takes precedence and shrinks
that uncertainty.

Offset sign convention: ``offset_ev = assigned_reference_ev - measured_e0_ev``,
i.e. ADD ``offset_ev`` to a measured energy to place it on the reference
scale.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from beamtimehero_cli import config as bl_config

CALIBRATION_FILENAME = "beamtimehero_energy_calibration.json"


def _store_path() -> Path:
    return Path(bl_config.BL_SCAN_DIR) / CALIBRATION_FILENAME


def load_records() -> list[dict]:
    path = _store_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return data.get("records", []) if isinstance(data, dict) else []


def record_calibration(
    element: str,
    edge: str,
    measured_e0_ev: float,
    measured_e0_unc_ev: float,
    assigned_reference_ev: float,
    reference_source: str,
    file_name: str,
    scan_numbers: list[int],
    e0_definition: str,
    notes: str = "",
) -> dict:
    """Append one calibration record and return it (with derived offset)."""
    record = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "element": element,
        "edge": edge.upper(),
        "measured_e0_ev": float(measured_e0_ev),
        "measured_e0_unc_ev": float(measured_e0_unc_ev),
        "assigned_reference_ev": float(assigned_reference_ev),
        "reference_source": reference_source,
        "offset_ev": float(assigned_reference_ev) - float(measured_e0_ev),
        "e0_definition": e0_definition,
        "file_name": file_name,
        "scan_numbers": scan_numbers,
        "notes": notes,
    }
    records = load_records()
    records.append(record)
    path = _store_path()
    path.write_text(json.dumps({"records": records}, indent=2))
    return record


def _age_hours(timestamp: str) -> float | None:
    try:
        then = datetime.fromisoformat(timestamp)
        return (datetime.now().astimezone() - then).total_seconds() / 3600.0
    except ValueError:
        return None


def current_calibration() -> dict:
    """Latest calibration plus drift across the record series.

    With no explicit record this returns an ASSUME-CALIBRATED result
    (``assumed: True``, ``offset_ev: 0.0``, ~0.2 eV systematic): per
    instrument spec the mono is foil-calibrated at beamtime start and
    step-loss drift is ``absev``-compensated, so edges are taken to sit at
    their tabulated positions. An explicit recorded calibration takes
    precedence and behaves as before.
    """
    records = load_records()
    if not records:
        return {
            "calibrated": True,
            "assumed": True,
            "offset_ev": 0.0,
            "measured_e0_unc_ev": 0.2,
            "reason": (
                "No explicit calibration record; per instrument spec the "
                "mono is foil-calibrated at beamtime start (absolute "
                "accuracy ~0.1-0.2 eV, step-loss compensated via absev), so "
                "edges are assumed to sit at their theoretical positions."
            ),
        }
    latest = records[-1]
    offsets = [r["offset_ev"] for r in records]
    result = {
        "calibrated": True,
        "offset_ev": latest["offset_ev"],
        "element": latest["element"],
        "edge": latest["edge"],
        "assigned_reference_ev": latest["assigned_reference_ev"],
        "measured_e0_unc_ev": latest.get("measured_e0_unc_ev"),
        "e0_definition": latest["e0_definition"],
        "reference_source": latest["reference_source"],
        "timestamp": latest["timestamp"],
        "age_hours": _age_hours(latest["timestamp"]),
        "n_records": len(records),
    }
    if len(records) > 1:
        result["drift"] = {
            "offset_range_ev": [min(offsets), max(offsets)],
            "offset_span_ev": max(offsets) - min(offsets),
            "first_timestamp": records[0]["timestamp"],
            "note": (
                "Span of calibration offsets across the session; if this "
                "approaches the valence signal (~1 eV), recalibrate before "
                "trusting absolute positions."
            ),
        }
    return result
