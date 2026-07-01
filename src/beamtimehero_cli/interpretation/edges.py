"""Element/edge metadata backed by xraydb's offline database.

First use of xraydb in this codebase. Tabulated edge energies here derive
from the Elam/Ravel/Sieber (2002) compilation shipped inside xraydb's
SQLite file — they are LABELS for locating/identifying an edge, NOT an
energy-calibration reference. Absolute edge-position chemistry requires a
session calibration record (see ``calibration_store``); tabulated values
carry compilation-dependent offsets at the 0.3-1 eV level (Bearden 1967
vs Deslattes 2003), comparable to the 1-3 eV/valence signal itself.
"""
from __future__ import annotations

import xraydb

EDGE_ENERGY_SOURCE = (
    "xraydb (Elam, Ravel & Sieber 2002, Radiat. Phys. Chem. 63, 121) — "
    "tabulated label, not an energy-calibration reference"
)

# Supported edge families (scope: XANES/HERFD near-edge only).
#   3d_K   — 3d transition-metal K-edges (Sc..Zn)
#   ln_L3  — lanthanide L3-edges (La..Lu)
#   5d_L3  — 5d / heavy-metal L3-edges (Hf..Bi)
#   an_L3  — actinide L3-edges (Ac..Cm)
#   an_M   — actinide M4/M5-edges
_3D_Z = range(21, 31)      # Sc..Zn
_LN_Z = range(57, 72)      # La..Lu
_5D_Z = range(72, 84)      # Hf..Bi
_AN_Z = range(89, 97)      # Ac..Cm


def classify_edge_family(element: str, edge: str) -> str:
    """Classify (element, edge) into an interpretation family.

    Returns one of ``3d_K``, ``ln_L3``, ``5d_L3``, ``an_L3``, ``an_M``,
    or ``other`` (measurable but outside the calibrated interpretation
    scope).
    """
    z = xraydb.atomic_number(element)
    edge = edge.upper()
    if edge == "K" and z in _3D_Z:
        return "3d_K"
    if edge == "L3":
        if z in _LN_Z:
            return "ln_L3"
        if z in _5D_Z:
            return "5d_L3"
        if z in _AN_Z:
            return "an_L3"
    if edge in ("M4", "M5") and z in _AN_Z:
        return "an_M"
    return "other"


def get_edge_info(element: str, edge: str) -> dict:
    """Tabulated metadata for one absorption edge (offline lookup)."""
    edge = edge.upper()
    info = xraydb.xray_edge(element, edge)
    if info is None:
        raise ValueError(f"Unknown edge '{edge}' for element '{element}'.")
    try:
        core_width = float(xraydb.core_width(element, edge))
    except Exception:
        core_width = None
    return {
        "element": element,
        "edge": edge,
        "family": classify_edge_family(element, edge),
        "tabulated_energy_ev": float(info.energy),
        "tabulated_energy_source": EDGE_ENERGY_SOURCE,
        "core_hole_width_ev": core_width,
        "fluorescence_yield": float(info.fyield),
    }


def _candidate_edges(e_min: float, e_max: float) -> list[dict]:
    """All in-scope edges whose tabulated energy lies inside [e_min, e_max]."""
    candidates = []
    scope = (
        [(z, "K") for z in _3D_Z]
        + [(z, "L3") for z in list(_LN_Z) + list(_5D_Z) + list(_AN_Z)]
        + [(z, e) for z in _AN_Z for e in ("M4", "M5")]
    )
    for z, edge in scope:
        el = xraydb.atomic_symbol(z)
        info = xraydb.xray_edge(el, edge)
        if info is None:
            continue
        if e_min <= info.energy <= e_max:
            candidates.append(get_edge_info(el, edge))
    return candidates


def suggest_edge(e_min: float, e_max: float) -> dict:
    """Suggest the most plausible edge for a scan energy window.

    A XANES scan places the edge in the lower part of its window (pre-edge
    below, XANES/near-EXAFS tail above), so candidates are ranked by
    distance from the 1/3 point of the window. The suggestion is a hint —
    tools accept an explicit element/edge override.
    """
    candidates = _candidate_edges(e_min, e_max)
    if not candidates:
        return {
            "found": False,
            "reason": (
                f"No in-scope edge (3d K, Ln/An L3, 5d L3, An M4/M5) has a "
                f"tabulated energy inside [{e_min:.1f}, {e_max:.1f}] eV. "
                "Pass element/edge explicitly."
            ),
        }
    anchor = e_min + (e_max - e_min) / 3.0
    candidates.sort(key=lambda c: abs(c["tabulated_energy_ev"] - anchor))
    return {
        "found": True,
        "best": candidates[0],
        "alternatives": candidates[1:4],
        "note": (
            "Auto-suggested from the scan energy window and tabulated edge "
            "energies (labels only, not calibration). Override with "
            "element/edge if wrong."
        ),
    }
