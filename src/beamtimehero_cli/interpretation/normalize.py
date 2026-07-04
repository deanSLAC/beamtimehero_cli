"""Normalization for HERFD intensity metrics.

The upstream pipeline (``analysis.xas.edge_step_normalize``) applies a
flat-anchor edge-step normalization — fine for spectral *shape*, but
Bugarin, Suarez Orduz & Glatzel (J. Synchrotron Rad. 31, 2024) show the
edge-step recipe biases HERFD intensities: HERFD has a negligible/flat
pre-edge background, so pre/post-edge anchoring introduces a spurious
scale. Area normalization over a window above E0 is accurate to <1% for
K-edges and ~2-10% for L3-edges, and is the default here for every
intensity metric. Which normalization produced a number is always
recorded in provenance.
"""
from __future__ import annotations

import numpy as np

AREA_NORM_CITATION = (
    "Bugarin, Suarez Orduz & Glatzel, 'Area normalization of HERFD-XANES "
    "spectra', J. Synchrotron Rad. 31 (2024)"
)

MBACK_CITATION = (
    "Weng, Waldo & Penner-Hahn, 'A method for normalization of X-ray "
    "absorption spectra', J. Synchrotron Rad. 12, 506 (2005)"
)

DEFAULT_AREA_WINDOW = (20.0, 100.0)  # eV above E0

# Preferred emission line (Siegbahn) per edge, used to centre the MBACK
# error-function step. Falls back to the strongest line starting with the
# edge letter, then to the edge energy itself.
_EDGE_EMISSION_LINES = {
    "K": ("Ka1", "Ka2"),
    "L1": ("Lb3", "Lb4"),
    "L2": ("Lb1",),
    "L3": ("La1", "La2"),
    "M4": ("Ma1", "Ma", "Mb"),
    "M5": ("Ma1", "Ma"),
}


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


def _emission_energy_ev(element: str, edge: str) -> float | None:
    """Strongest fluorescence-line energy (eV) for an edge, via xraydb.

    Returns ``None`` if no line can be resolved (the caller falls back to
    the edge energy). Never raises.
    """
    try:
        import xraydb
        lines = xraydb.xray_lines(element)
    except Exception:
        return None
    if not lines:
        return None
    for name in _EDGE_EMISSION_LINES.get(edge.upper(), ()):
        if name in lines:
            return float(lines[name].energy)
    letter = edge[:1].upper()
    cand = [ln for nm, ln in lines.items() if nm.startswith(letter)]
    if cand:
        return float(max(cand, key=lambda ln: ln.intensity).energy)
    return None


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
