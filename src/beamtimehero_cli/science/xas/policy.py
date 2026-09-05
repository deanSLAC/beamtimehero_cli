"""XAS analysis policy — the defaults and heuristics, in one place.

Everything here is a scientific *choice* rather than a computation: which fit
windows to use, how many white-line components an edge family needs, how the
absorber element is guessed when the caller does not say, and how much data a
descriptor fit needs before it is trustworthy.

These lived inline in the tool handlers (``tool_catalog/tools_core.py``),
several of them duplicated across handlers. They are collected here so that
changing a default is a one-line edit in an obvious file, and so each choice
can carry the citation that justifies it.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Fit windows, relative to E0 (eV)
# ---------------------------------------------------------------------------

# Wilke-style pre-edge window: far enough below the edge to exclude the rising
# edge, close enough to contain the 1s->3d pre-edge features. Wilke et al.
# (2001) Am. Mineral. 86, 714.
PRE_EDGE_WINDOW_REL = (-20.0, -5.0)

# White-line window: spans the edge crest and the first post-edge oscillation.
WHITE_LINE_WINDOW_REL = (-10.0, 40.0)


# ---------------------------------------------------------------------------
# White-line component count
# ---------------------------------------------------------------------------

# Edge families whose white line is not a single peak:
#   ln_L3 — Ce(IV) shows a final-state 4f^0/4f^1 doublet
#   an_L3 / an_M — U(VI) M4 carries satellite structure
# Everything else is fit with a single pseudo-Voigt.
# Refs: Bugarin & Glatzel (2024) for the HERFD intensity treatment;
#       Bes et al. (2016) J. Nucl. Mater. 476, 261 for the U M4 method.
MULTI_COMPONENT_FAMILIES = ("ln_L3", "an_L3", "an_M")

MULTI_COMPONENT_COUNT = 3
SINGLE_COMPONENT_COUNT = 1


def white_line_components_for(family: str | None) -> int:
    """Max pseudo-Voigt components to fit the white line of this edge family."""
    return (
        MULTI_COMPONENT_COUNT
        if family in MULTI_COMPONENT_FAMILIES
        else SINGLE_COMPONENT_COUNT
    )


# ---------------------------------------------------------------------------
# Data adequacy
# ---------------------------------------------------------------------------

# Below this many energy points shared across the selected scans, the
# descriptor fits (pre-edge, white line, derivative E0) are not meaningful.
MIN_OVERLAPPING_POINTS = 20


def check_overlap(n_points: int) -> None:
    """Raise ValueError when too few shared energy points remain to fit."""
    if n_points < MIN_OVERLAPPING_POINTS:
        raise ValueError(
            "Too few overlapping energy points across the selected scans "
            f"({n_points}) for descriptor fits."
        )


# ---------------------------------------------------------------------------
# Absolute -> relative fit windows
# ---------------------------------------------------------------------------

def window_rel_from_absolute(
    energy, mu, e_min: float, e_max: float,
) -> tuple[float, float]:
    """Convert an absolute-eV fit window to one relative to the measured E0.

    Callers express window overrides in absolute eV (that is what a scientist
    reads off a plot); the fitters take windows relative to E0. E0 is measured
    from the spectrum rather than assumed, so an override stays anchored to
    this spectrum's edge.
    """
    from beamtimehero_cli.science.xas.e0 import find_e0

    e0 = float(find_e0(energy, mu)["e0_ev"])
    return (float(e_min) - e0, float(e_max) - e0)


# ---------------------------------------------------------------------------
# Absorber element / edge resolution
# ---------------------------------------------------------------------------

def resolve_edge(
    energy, mu, element: str | None = None, edge: str | None = None,
) -> dict:
    """Resolve which absorption edge a spectrum measures.

    With both ``element`` and ``edge`` given, the assignment is taken as
    stated. With neither, it is inferred from the scan's energy window.

    Auto-detection is anchored on the *measured* E0 whenever the derivative
    fit succeeds: the energy-window one-third-point proxy misranks neighbouring
    edges 20-30 eV apart (Ni K vs Er L3) whenever the scan carries a long
    post-edge tail. The proxy is only the fallback.

    Returns the edge-info dict with a ``detection`` key recording which route
    was taken, plus ambiguity flags when two candidates score close together.

    Raises ValueError if only one of element/edge is given, or if no candidate
    edge fits the scan's energy range.
    """
    from beamtimehero_cli.science.tables import edges as edge_tables

    if element and edge:
        info = edge_tables.get_edge_info(element, edge)
        info["detection"] = "explicit"
        return info
    if element or edge:
        raise ValueError("Pass BOTH element and edge, or neither (auto-detect).")

    try:
        from beamtimehero_cli.science.xas.e0 import find_e0
        e0_anchor = float(find_e0(energy, mu)["e0_ev"])
    except Exception:  # noqa: BLE001 — un-fittable spectra fall back to the window
        e0_anchor = None

    suggestion = edge_tables.suggest_edge(
        float(min(energy)), float(max(energy)), e0_ev=e0_anchor)
    if not suggestion["found"]:
        raise ValueError(suggestion["reason"])

    info = suggestion["best"]
    info["detection"] = (
        "auto_from_measured_e0"
        if suggestion.get("anchor_source") == "measured_e0"
        else "auto_from_energy_window"
    )
    if suggestion.get("ambiguous"):
        info["ambiguous"] = True
        info["competing_edges"] = suggestion.get("competing", [])
        info["detection_note"] = suggestion["note"]
    return info

# ---------------------------------------------------------------------------
# CITATIONS — method -> reference. ``None`` means the method is implemented
# but not yet attributed; those surface as gaps on the generated science
# index, and filling one in is a welcome contribution. See science/README.md.
# ---------------------------------------------------------------------------

CITATIONS = {
    "Pre-edge fit window": (
        "Wilke, Farges, Petit, Brown & Martin, Am. Mineral. 86, 714-730 "
        "(2001), DOI 10.2138/am-2001-5-612."
    ),
    "Multi-component white-line families (Ce(IV) doublet, U(VI) satellites)": (
        "Bugarin, Suarez Orduz & Glatzel, J. Synchrotron Rad. 31 (2024); "
        "Bes et al., Inorg. Chem. 55, 4260 (2016)."
    ),
    "White-line fit window": None,
    "Minimum overlapping points for a descriptor fit": None,
    "E0-anchored edge auto-detection": None,
}
