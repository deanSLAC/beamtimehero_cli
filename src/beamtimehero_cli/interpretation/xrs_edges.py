"""Edge metadata for XRS — the low-Z / shallow edges XRS is used to reach.

XRS accesses absorption edges on an ENERGY-LOSS axis, so the accessible set is
the shallow edges that conventional hard-XAS can't reach and soft-XAS can only
reach at the surface (Li/B/C/N/O/F K, Si/P/S L, and 3d transition-metal L
edges). Energies are tabulated labels (xraydb offline, with a curated fallback);
they locate/identify an edge but are NOT an energy-loss calibration reference —
that comes from the elastic line (see ``spec_data.xrs_data``).
"""
from __future__ import annotations

# Curated fallback of common XRS edges (energy loss ≈ edge energy, eV) and their
# interpretation family. Used when xraydb lacks an entry; xraydb wins when it has
# one. Sources: Sahle 2015; standard soft-X-ray edge tables.
_XRS_EDGES = {
    ("Li", "K"): (54.7, "low_Z_K"),
    ("B", "K"): (187.9, "low_Z_K"),
    ("C", "K"): (284.2, "low_Z_K"),
    ("N", "K"): (401.6, "low_Z_K"),
    ("O", "K"): (543.1, "low_Z_K"),
    ("F", "K"): (696.7, "low_Z_K"),
    ("Si", "L3"): (99.8, "main_L"),
    ("P", "L3"): (130.0, "main_L"),
    ("S", "L3"): (162.5, "main_L"),
    # 3d transition-metal L3 edges (branching-ratio interpretation)
    ("Ti", "L3"): (455.5, "3d_L"),
    ("V", "L3"): (512.1, "3d_L"),
    ("Cr", "L3"): (574.1, "3d_L"),
    ("Mn", "L3"): (638.7, "3d_L"),
    ("Fe", "L3"): (706.8, "3d_L"),
    ("Co", "L3"): (778.1, "3d_L"),
    ("Ni", "L3"): (852.7, "3d_L"),
    ("Cu", "L3"): (932.7, "3d_L"),
}

_3D_L = {"Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn"}


def classify_xrs_family(element: str, edge: str) -> str:
    """Interpretation family for an XRS edge.

    ``low_Z_K`` (Li/B/C/N/O/F K — pre-edge / π*-σ* / white-line chemistry),
    ``3d_L`` (transition-metal L2,3 — branching ratio → oxidation state),
    ``main_L`` (Si/P/S L), or ``other``.
    """
    edge = edge.upper()
    if edge == "K" and element in ("Li", "B", "C", "N", "O", "F"):
        return "low_Z_K"
    if edge in ("L3", "L2", "L23") and element in _3D_L:
        return "3d_L"
    if edge in ("L3", "L2", "L23") and element in ("Si", "P", "S"):
        return "main_L"
    return "other"


def get_xrs_edge_info(element: str, edge: str) -> dict:
    """Tabulated loss/energy label + interpretation family for one XRS edge."""
    edge = edge.upper()
    energy = None
    source = "curated XRS edge table"
    try:
        import xraydb
        info = xraydb.xray_edge(element, edge)
        if info is not None:
            energy = float(info.energy)
            source = "xraydb (Elam/Ravel/Sieber 2002) tabulated label"
    except Exception:
        pass
    if energy is None:
        key = (element, edge)
        if key in _XRS_EDGES:
            energy = _XRS_EDGES[key][0]
        else:
            raise ValueError(f"No tabulated XRS edge for '{element}' '{edge}'.")
    return {
        "element": element,
        "edge": edge,
        "family": classify_xrs_family(element, edge),
        "tabulated_energy_ev": energy,
        "tabulated_energy_source": source,
    }


# Near-tie margin (eV): when the two closest curated edges land within this
# distance difference of the anchor, the pick is reported as ambiguous.
_AMBIGUITY_MARGIN_EV = 8.0


def suggest_xrs_edge(loss_min: float, loss_max: float,
                     onset_ev: float | None = None) -> dict:
    """Suggest the most plausible XRS edge for an energy-loss window.

    The anchor is the measured edge onset when the caller has one, else the
    1/3 point of the window (the onset sits in the lower third of a
    well-planned loss scan; Compton background above). A near-tie between
    two curated edges is reported as ``ambiguous`` with a ``competing``
    list so callers can require an explicit element/edge instead of
    narrating the wrong edge. Returns ``{found, best, alternatives, ...}``
    or ``{found: False, reason}``.
    """
    candidates = []
    for (el, edge), (energy, _fam) in _XRS_EDGES.items():
        if loss_min <= energy <= loss_max:
            candidates.append(get_xrs_edge_info(el, edge))
    if not candidates:
        return {
            "found": False,
            "reason": (
                f"No curated XRS edge has a tabulated loss inside "
                f"[{loss_min:.1f}, {loss_max:.1f}] eV. Pass element/edge explicitly."
            ),
        }
    anchor = float(onset_ev) if onset_ev is not None \
        else loss_min + (loss_max - loss_min) / 3.0
    candidates.sort(key=lambda c: abs(c["tabulated_energy_ev"] - anchor))
    dists = [abs(c["tabulated_energy_ev"] - anchor) for c in candidates]
    ambiguous = len(candidates) > 1 and (dists[1] - dists[0]) < _AMBIGUITY_MARGIN_EV
    out = {
        "found": True,
        "best": candidates[0],
        "alternatives": candidates[1:4],
        "anchor_ev": round(anchor, 2),
        "anchor_source": "measured_onset" if onset_ev is not None else "window_third",
        "ambiguous": ambiguous,
        "note": (
            "Auto-suggested from the loss window and tabulated edge labels "
            "(not calibration). Override with element/edge if wrong."
        ),
    }
    if ambiguous:
        out["competing"] = [
            {"element": c["element"], "edge": c["edge"],
             "tabulated_energy_ev": c["tabulated_energy_ev"]}
            for c in candidates[:3]
        ]
        out["note"] = (
            "AMBIGUOUS auto-detection: two or more curated edges sit "
            "comparably close to this loss window. Pass element/edge "
            "explicitly rather than trusting this pick. " + out["note"]
        )
    return out
