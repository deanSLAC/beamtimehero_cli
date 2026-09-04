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
#   3d_K          — 3d transition-metal K-edges (Sc..Zn)
#   4d_K          — 4d transition-metal K-edges (Y..Cd)
#   5d_K          — 5d transition-metal K-edges (Hf..Au)
#   main_group_K  — s/p-block K-edges (K, Ca, Ga..Sr, In..Ba)
#   ln_L3  — lanthanide L3-edges (La..Lu)
#   5d_L3  — 5d / heavy-metal L3-edges (Hf..Bi)
#   an_L3  — actinide L3-edges (Ac..Cm)
#   an_M   — actinide M4/M5-edges
_3D_Z = range(21, 31)      # Sc..Zn
_4D_Z = range(39, 49)      # Y..Cd
_5D_K_Z = range(72, 80)    # Hf..Au (K-edge scope; the 5d L3 set below runs to Bi)
# s/p-block K edges reachable by hard XAS. Without these, an As or Se K scan
# has NO in-scope K candidate and auto-detection silently picks a lanthanide
# or Au L3 in the same window (the George-campaign As->Au L3 failure).
_MAIN_GROUP_K_Z = (
    list(range(19, 21))    # K, Ca
    + list(range(31, 39))  # Ga..Sr (Ga Ge As Se Br Kr Rb Sr)
    + list(range(49, 57))  # In..Ba (In Sn Sb Te I Xe Cs Ba)
)
_LN_Z = range(57, 72)      # La..Lu
_5D_Z = range(72, 84)      # Hf..Bi
_AN_Z = range(89, 97)      # Ac..Cm

# Elements commonly measured at SSRL chemistry/catalysis beamlines — a weak
# prior used ONLY to break near-ties in window auto-detection, never to
# override a clearly closer edge.
_COMMON_ABSORBERS = frozenset({
    "K", "Ca", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Ga", "Ge", "As", "Se", "Br", "Sr", "Y", "Zr", "Nb", "Mo", "Ru",
    "Rh", "Pd", "Ag", "Cd", "Sn", "Sb", "I", "W", "Re", "Ir", "Pt",
    "Au", "Hg", "Pb", "Bi", "La", "Ce", "Gd", "U",
})


def classify_edge_family(element: str, edge: str) -> str:
    """Classify (element, edge) into an interpretation family.

    Returns one of ``3d_K``, ``4d_K``, ``5d_K``, ``main_group_K``,
    ``ln_L3``, ``5d_L3``, ``an_L3``, ``an_M``, or ``other`` (measurable
    but outside the calibrated interpretation scope).
    """
    z = xraydb.atomic_number(element)
    edge = edge.upper()
    if edge == "K" and z in _3D_Z:
        return "3d_K"
    if edge == "K" and z in _4D_Z:
        return "4d_K"
    if edge == "K" and z in _5D_K_Z:
        return "5d_K"
    if edge == "K" and z in _MAIN_GROUP_K_Z:
        return "main_group_K"
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
        [(z, "K") for z in list(_3D_Z) + list(_4D_Z) + list(_5D_K_Z)
         + _MAIN_GROUP_K_Z]
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


# Scoring knobs for suggest_edge. The distance term is scaled by _TOL_EV per
# score point; a K-edge outranks an equally-distant L3/M edge by
# _K_EDGE_BONUS * _TOL_EV eV (K is the overwhelmingly common hard-XAS choice
# at these energies), and a common absorber outranks an exotic one by
# _COMMON_BONUS * _TOL_EV eV. With a measured-E0 anchor the distance term
# dominates as it should; the bonuses only settle window-shape ambiguity.
_TOL_EV = 15.0
_K_EDGE_BONUS = 2.0
_COMMON_BONUS = 1.0
_AMBIGUITY_MARGIN = 0.5


def _suggestion_score(cand: dict, anchor: float) -> float:
    score = -abs(cand["tabulated_energy_ev"] - anchor) / _TOL_EV
    if cand["edge"] == "K":
        score += _K_EDGE_BONUS
    if cand["element"] in _COMMON_ABSORBERS:
        score += _COMMON_BONUS
    return score


def suggest_edge(e_min: float, e_max: float,
                 e0_ev: float | None = None) -> dict:
    """Suggest the most plausible edge for a scan energy window.

    The anchor is the measured E0 when the caller has one (the reliable
    signal — window shape varies with how much post-edge tail was scanned),
    else the 1/3 point of the window (a XANES scan places the edge in the
    lower part: pre-edge below, XANES/near-EXAFS tail above). Candidates
    are scored by distance to the anchor with a weak prior toward K edges
    and common absorbers; a near-tie is reported as ``ambiguous`` with the
    ``competing`` list so callers can ask for an explicit element/edge
    instead of narrating the wrong element's chemistry. The suggestion is
    a hint — tools accept an explicit element/edge override.
    """
    candidates = _candidate_edges(e_min, e_max)
    if not candidates:
        return {
            "found": False,
            "reason": (
                f"No in-scope edge (3d/4d/5d/main-group K, Ln/An L3, 5d L3, "
                f"An M4/M5) has a tabulated energy inside "
                f"[{e_min:.1f}, {e_max:.1f}] eV. Pass element/edge "
                "explicitly."
            ),
        }
    anchor = float(e0_ev) if e0_ev is not None else e_min + (e_max - e_min) / 3.0
    candidates.sort(key=lambda c: _suggestion_score(c, anchor), reverse=True)
    scores = [_suggestion_score(c, anchor) for c in candidates]
    ambiguous = len(candidates) > 1 and (scores[0] - scores[1]) < _AMBIGUITY_MARGIN
    out = {
        "found": True,
        "best": candidates[0],
        "alternatives": candidates[1:4],
        "anchor_ev": round(anchor, 2),
        "anchor_source": "measured_e0" if e0_ev is not None else "window_third",
        "ambiguous": ambiguous,
        "note": (
            "Auto-suggested from the scan energy window and tabulated edge "
            "energies (labels only, not calibration). Override with "
            "element/edge if wrong."
        ),
    }
    if ambiguous:
        out["competing"] = [
            {"element": c["element"], "edge": c["edge"],
             "tabulated_energy_ev": c["tabulated_energy_ev"]}
            for c in candidates[:3]
        ]
        out["note"] = (
            "AMBIGUOUS auto-detection: two or more edges score comparably "
            "for this window. Pass element/edge explicitly rather than "
            "trusting this pick. " + out["note"]
        )
    return out
