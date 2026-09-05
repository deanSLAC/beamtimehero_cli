"""Rigorous XAS intensity normalization for HERFD metrics.

``area_normalize`` (Bugarin & Glatzel 2024) is the HERFD default; ``mback_normalize``
fits the tabulated mass-absorption coefficient (Weng & Penner-Hahn 2005);
``pre_post_normalize`` is the Athena-style pre-edge/post-edge treatment.

For the naive per-scan edge-step used by the generic scan tools see
:mod:`beamtimehero_cli.science.reduce.normalize`.
"""
from __future__ import annotations

import numpy as np

from beamtimehero_cli.science.tables.emission_lines import (
    emission_energy_ev as _emission_energy_ev,
)


AREA_NORM_CITATION = (
    "Bugarin, Suarez Orduz & Glatzel, 'Area normalization of HERFD-XANES "
    "spectra', J. Synchrotron Rad. 31 (2024)"
)

MBACK_CITATION = (
    "Weng, Waldo & Penner-Hahn, 'A method for normalization of X-ray "
    "absorption spectra', J. Synchrotron Rad. 12, 506 (2005)"
)

DEFAULT_AREA_WINDOW = (20.0, 100.0)  # eV above E0

def area_normalize(
    energy: np.ndarray,
    mu: np.ndarray,
    e0: float,
    window: tuple[float, float] = DEFAULT_AREA_WINDOW,
    min_span_ev: float = 15.0,
) -> tuple[np.ndarray, dict]:
    """Rescale mu so its mean over [e0+window[0], e0+window[1]] equals 1.

    Input is assumed already offset-corrected (pre-edge ~0), which the
    upstream edge-step normalization guarantees. Returns
    ``(mu_normalized, provenance)``. If the window (clipped to the data)
    spans less than ``min_span_ev``, the spectrum is returned unchanged
    with ``provenance["applied"] = False`` — a short scan cannot support
    area normalization and silently pretending otherwise would corrupt
    every downstream intensity.
    """
    lo = e0 + window[0]
    hi = min(e0 + window[1], float(energy[-1]))
    sel = (energy >= lo) & (energy <= hi)
    span = hi - lo
    provenance = {
        "method": "area",
        "window_ev_above_e0": [float(window[0]), float(window[1])],
        "window_used_ev": [float(lo), float(hi)],
        "citation": AREA_NORM_CITATION,
    }
    if span < min_span_ev or sel.sum() < 5:
        provenance.update({
            "applied": False,
            "reason": (
                f"post-edge window spans only {span:.1f} eV "
                f"({int(sel.sum())} points); need >= {min_span_ev} eV. "
                "Intensities remain edge-step normalized."
            ),
        })
        return mu, provenance
    scale = float(np.trapezoid(mu[sel], energy[sel]) / (energy[sel][-1] - energy[sel][0]))
    if not np.isfinite(scale) or scale <= 0:
        provenance.update({"applied": False, "reason": "non-positive window area"})
        return mu, provenance
    provenance.update({"applied": True, "scale": scale})
    return mu / scale, provenance


def edge_step_provenance() -> dict:
    """Provenance stamp for spectra left on the upstream normalization."""
    return {
        "method": "edge_step_flat_anchor",
        "applied": True,
        "note": (
            "Upstream flat-anchor edge-step normalization (mean of first/"
            "last 10% of points). Adequate for shape/positions; HERFD "
            "intensity comparisons prefer area normalization "
            f"({AREA_NORM_CITATION})."
        ),
    }

def mback_normalize(
    energy: np.ndarray,
    mu: np.ndarray,
    e0: float,
    element: str | None,
    edge: str | None,
    *,
    poly_order: int = 2,
    pre_gap_ev: float = 15.0,
    post_gap_ev: float = 30.0,
    min_region_points: int = 5,
) -> tuple[np.ndarray, dict]:
    """MBACK normalization (Weng, Waldo & Penner-Hahn 2005).

    Fits ``scale*mu + amp*erfc((E-Efluo)/xi) + polynomial(E-E0)`` to the
    xraydb-tabulated mass-absorption coefficient over the pre- and
    post-edge regions (the XANES between them is excluded), then returns
    the background-corrected spectrum on a unit-edge-step scale — the same
    ~[0, 1] scale as ``area_normalize``/``edge_step`` so downstream fits
    and intensity brackets stay comparable.

    Mirrors :func:`area_normalize`'s contract: returns ``(mu_normalized,
    provenance)`` and, on *any* failure or non-convergence, returns ``mu``
    unchanged with ``provenance["applied"] = False`` and a ``reason``. It
    never raises and never emits an unvetted fit — the source MATLAB port
    (xas-data-analysis) skipped the convergence check; this does not.

    The tabulated-mu energy axis is shifted so its edge aligns with the
    observed ``e0`` before fitting, so an eV-scale mono offset (the size of
    the valence signal itself) does not corrupt the background match.
    Unlike a hardcoded element table, the tabulated mu comes straight from
    xraydb, so every element/edge the beamline measures is covered.
    """
    provenance = {
        "method": "mback",
        "citation": MBACK_CITATION,
        "tabulated_source": "xraydb.mu_elam (Elam 2002), total attenuation",
        "element": element,
        "edge": edge,
    }
    energy = np.asarray(energy, dtype=float)
    mu = np.asarray(mu, dtype=float)

    def _refuse(reason: str) -> tuple[np.ndarray, dict]:
        provenance.update({"applied": False, "reason": reason})
        return mu, provenance

    if not element or not edge:
        return _refuse("MBACK requires a known element and edge; none resolved.")
    if energy.size < 2 * min_region_points + 5 or not np.all(np.isfinite(mu)):
        return _refuse("too few points or non-finite spectrum for an MBACK fit.")

    try:
        from scipy.optimize import least_squares
        from scipy.special import erfc
        import xraydb

        edge_rec = xraydb.xray_edge(element, edge.upper())
        e_edge_tab = float(edge_rec.energy)
        shift = float(e0) - e_edge_tab
        mu_tab_raw = np.asarray(
            xraydb.mu_elam(element, energy - shift, kind="total"), dtype=float
        )
    except Exception as exc:  # xraydb/scipy failure -> degrade, never crash
        return _refuse(f"xraydb/scipy lookup failed: {exc}")

    if not np.all(np.isfinite(mu_tab_raw)):
        return _refuse("tabulated mu contained non-finite values.")

    e_fluo_tab = _emission_energy_ev(element, edge)
    e_fluo = (e_fluo_tab + shift) if e_fluo_tab is not None else float(e0)

    # Pre-edge quadratic subtraction of the tabulated mu, zeroed below edge.
    below = energy < float(e0)
    if int(below.sum()) >= 3:
        pre_fit = np.polyfit(energy[below], mu_tab_raw[below], 2)
        mu_tab = mu_tab_raw - np.polyval(pre_fit, energy)
        mu_tab[below] = 0.0
    else:
        mu_tab = mu_tab_raw - float(np.min(mu_tab_raw))

    # Fit regions relative to the observed edge (XANES excluded).
    idx_pre = energy <= (float(e0) - pre_gap_ev)
    idx_post = energy >= (float(e0) + post_gap_ev)
    idx_fit = idx_pre | idx_post
    idx_xane = (~idx_pre) & (~idx_post)
    n_pre, n_post = int(idx_pre.sum()), int(idx_post.sum())
    if n_pre < min_region_points or n_post < min_region_points:
        return _refuse(
            f"pre/post-edge fit regions too small (pre={n_pre}, post={n_post}; "
            f"need >= {min_region_points} each)."
        )

    # Scale data and tabulated mu into comparable ranges over the XANES.
    mu_span = float(np.max(mu_tab[idx_xane])) if idx_xane.any() else float(np.max(mu_tab))
    if not np.isfinite(mu_span) or mu_span <= 0:
        mu_span = 1.0
    raw_span = float(np.ptp(mu[idx_xane])) if idx_xane.any() else float(np.ptp(mu))
    if raw_span == 0 or not np.isfinite(raw_span):
        raw_span = 1.0
    mu_tab_s = mu_tab / mu_span
    raw_s = mu / raw_span

    # sqrt(n) region weights equalize pre/post influence. Energy is ascending
    # and the pre region lies entirely below the post region, so the
    # positional split matches the boolean-mask ordering of idx_fit.
    weights = np.empty(n_pre + n_post)
    weights[:n_pre] = 1.0 / np.sqrt(n_pre)
    weights[n_pre:] = 1.0 / np.sqrt(n_post)

    def _model(params: np.ndarray) -> np.ndarray:
        scale, amp, xi = params[0], params[1], params[2]
        poly = params[3:]
        return (
            scale * raw_s
            + amp * erfc((energy - e_fluo) / xi)
            + np.polyval(poly, energy - float(e0))
        )

    def _residual(params: np.ndarray) -> np.ndarray:
        return (_model(params)[idx_fit] - mu_tab_s[idx_fit]) * weights

    try:
        poly_init = np.polyfit(energy[idx_post] - float(e0), mu_tab_s[idx_post], poly_order)
    except Exception:
        poly_init = np.zeros(poly_order + 1)
    p0 = [1.0, -0.5, 50.0] + list(poly_init[:-1]) + [0.0]
    lb = [0.0, -np.inf, 1.0] + [-np.inf] * (poly_order + 1)
    ub = [np.inf, 0.0, np.inf] + [np.inf] * (poly_order + 1)

    try:
        result = least_squares(
            _residual, p0, bounds=(lb, ub), method="trf", max_nfev=2000,
        )
    except Exception as exc:
        return _refuse(f"MBACK least-squares raised: {exc}")
    if not result.success:
        return _refuse(f"MBACK fit did not converge (status {result.status}).")

    mu_norm = _model(result.x)
    if not np.all(np.isfinite(mu_norm)):
        return _refuse("MBACK produced a non-finite spectrum.")

    provenance.update({
        "applied": True,
        "e_edge_tabulated_ev": e_edge_tab,
        "e0_aligned_ev": float(e0),
        "edge_shift_ev": shift,
        "e_fluo_ev": e_fluo,
        "poly_order": poly_order,
        "fit_regions_ev": {
            "pre": [float(energy[idx_pre][0]), float(energy[idx_pre][-1])],
            "post": [float(energy[idx_post][0]), float(energy[idx_post][-1])],
        },
        "rms_residual": float(np.sqrt(np.mean(_residual(result.x) ** 2))),
    })
    return mu_norm, provenance


# ---------------------------------------------------------------------------
# Pre/post-edge polynomial normalization (Athena-style, EXAFS-ready)
# ---------------------------------------------------------------------------

def pre_post_normalize(
    energy: np.ndarray,
    mu: np.ndarray,
    e0: float,
    pre1: float | None = None,
    pre2: float | None = None,
    norm1: float | None = None,
    norm2: float | None = None,
    norm_order: int = 2,
    flatten: bool = True,
) -> tuple[np.ndarray, dict]:
    """Athena-style edge-step normalization: pre-edge line + post-edge poly.

    Fits a line over [e0+pre1, e0+pre2] (pre1 < pre2 < 0) and a polynomial
    of ``norm_order`` over [e0+norm1, e0+norm2]; the edge step is their
    difference at E0. With ``flatten`` the post-edge curvature above E0 is
    removed (Athena's "flattened" spectrum), which is what EXAFS extraction
    and operando-overlay comparisons want.

    This differs from the flat-anchor ``analysis.xas.edge_step_normalize``
    (mean of first/last 10% of points): the polynomial version tolerates
    sloping pre-edges and the long curved post-edge of an EXAFS-length scan.
    Window defaults scale to the scan range when not given.

    Mirrors :func:`area_normalize`'s contract: returns ``(mu_normalized,
    provenance)`` and on failure returns ``mu`` unchanged with
    ``provenance["applied"] = False`` and a ``reason``; never raises. The
    edge step is reported in ``provenance["edge_step"]``.
    """
    energy = np.asarray(energy, dtype=float)
    mu = np.asarray(mu, dtype=float)
    e0 = float(e0)
    provenance: dict = {"method": "pre_post_edge_polynomial", "e0_ev": e0}

    def _refuse(reason: str) -> tuple[np.ndarray, dict]:
        provenance.update({"applied": False, "reason": reason})
        return mu, provenance

    if energy.size < 15 or not np.all(np.isfinite(mu)):
        return _refuse("too few points or non-finite spectrum.")

    if pre1 is None:
        pre1 = max(float(energy.min()) - e0, -200.0) * 0.9
    if pre2 is None:
        pre2 = pre1 / 3.0
    if norm2 is None:
        norm2 = (float(energy.max()) - e0) * 0.95
    if norm1 is None:
        norm1 = min(100.0, norm2 / 3.0)
    if not (pre1 < pre2 < 0 < norm1 < norm2):
        return _refuse(
            f"window ordering violated (pre1={pre1:.1f}, pre2={pre2:.1f}, "
            f"norm1={norm1:.1f}, norm2={norm2:.1f} relative to E0)."
        )

    pre_sel = (energy >= e0 + pre1) & (energy <= e0 + pre2)
    if int(pre_sel.sum()) < 2:
        pre_sel = energy < e0 - 10
    post_sel = (energy >= e0 + norm1) & (energy <= e0 + norm2)
    order = int(norm_order)
    if int(post_sel.sum()) < order + 2:
        post_sel = energy > e0 + 20
        order = 1
    if int(pre_sel.sum()) < 2 or int(post_sel.sum()) < order + 2:
        return _refuse(
            f"pre/post-edge regions too small (pre={int(pre_sel.sum())}, "
            f"post={int(post_sel.sum())})."
        )

    pre_line = np.polyval(np.polyfit(energy[pre_sel], mu[pre_sel], 1), energy)
    post_poly = np.polyval(
        np.polyfit(energy[post_sel] - e0, mu[post_sel], order), energy - e0
    )
    i0e = int(np.argmin(np.abs(energy - e0)))
    edge_step = float(post_poly[i0e] - pre_line[i0e])
    if not np.isfinite(edge_step) or edge_step == 0:
        return _refuse("degenerate edge step (zero or non-finite).")

    norm = (mu - pre_line) / edge_step
    if flatten:
        out = norm.copy()
        above = energy >= e0
        out[above] = norm[above] - (
            (post_poly[above] - pre_line[above] - edge_step) / edge_step
        )
    else:
        out = norm

    provenance.update({
        "applied": True,
        "edge_step": edge_step,
        "flattened": bool(flatten),
        "pre_edge_window_rel_ev": [float(pre1), float(pre2)],
        "norm_window_rel_ev": [float(norm1), float(norm2)],
        "norm_poly_order": order,
        "note": (
            "Athena-style pre-edge line + post-edge polynomial; edge step "
            "from their difference at E0. Negative edge_step means the "
            "channel has no absorption edge (wrong counter or inverted "
            "signal)."
        ),
    })
    return out, provenance

# ---------------------------------------------------------------------------
# CITATIONS — method -> reference. ``None`` means the method is implemented
# but not yet attributed; those surface as gaps on the generated science
# index, and filling one in is a welcome contribution. See science/README.md.
# ---------------------------------------------------------------------------

CITATIONS = {
    "Area normalization (the HERFD default)": AREA_NORM_CITATION,
    "MBACK normalization": MBACK_CITATION,
    "Athena-style pre-edge/post-edge normalization": None,
}
