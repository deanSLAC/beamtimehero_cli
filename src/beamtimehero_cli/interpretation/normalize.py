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
