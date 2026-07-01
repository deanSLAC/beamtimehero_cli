"""Session energy-calibration record.

The one place in ``interpretation/`` that touches the filesystem: a JSON
record in the scan directory documenting how the mono energy axis maps to
a chosen reference convention (a measured foil/compound scan with a cited
assigned E0). Interpretation tools read this record and REFUSE absolute
oxidation-state estimates when it is absent — monochromator offset/drift
is eV-scale (Jones et al., J. Synchrotron Rad. 27, 2020), the same size
as the valence signal.

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

    Returns ``{"calibrated": False, ...}`` when no record exists — the
    signal for interpretation tools to run in relative-only mode.
    """
    records = load_records()
    if not records:
        return {
            "calibrated": False,
            "reason": (
                "No session energy calibration recorded. Run "
                "record_energy_calibration on a measured reference "
                "foil/compound scan first. Absolute edge/centroid "
                "positions are meaningless without it (mono offset/drift "
                "is eV-scale)."
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
