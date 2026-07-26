"""Linear-combination fitting (LCF) — axis-agnostic, pure math.

Promoted from ``interpretation/xrs_interpret.compare_xrs_to_references``
(which now delegates here): the nnls fit never depended on the energy-loss
axis, so it belongs in the generic branch. Pass any monotonic axis —
energy loss (XRS), energy (XANES mu(E)), even k (chi) — as ``axis``.

Technique-specific caveats (e.g. the XRS low-q dipole-regime warning) are
the caller's to add; this module reports only the fit.
"""
from __future__ import annotations

import numpy as np


def compare_to_references(axis, intensity, references: list[dict]) -> dict:
    """Non-negative linear-combination fit of a spectrum to reference spectra.

    ``references`` = list of ``{"name", "axis", "intensity"}`` (the legacy
    XRS key ``"loss"`` is accepted as an alias for ``"axis"``). All are
    interpolated onto the target axis, then fit with non-negative least
    squares; fractions are normalized to sum 1. Returns fractions + fit
    residual, or ``{"error": ...}`` on degenerate input.
    """
    from scipy.optimize import nnls

    axis = np.asarray(axis, dtype=float)
    intensity = np.asarray(intensity, dtype=float)
    ok = np.isfinite(axis) & np.isfinite(intensity)
    axis, intensity = axis[ok], intensity[ok]
    if len(references) < 1 or axis.size < 3:
        return {"error": "Need a spectrum and ≥1 reference."}
    cols, names = [], []
    for ref in references:
        raxis = ref.get("axis", ref.get("loss"))
        rl = np.asarray(raxis, dtype=float)
        ri = np.asarray(ref["intensity"], dtype=float)
        cols.append(np.interp(axis, rl, ri, left=np.nan, right=np.nan))
        names.append(ref.get("name", f"ref{len(names)}"))
    A = np.vstack(cols).T
    good = np.all(np.isfinite(A), axis=1) & np.isfinite(intensity)
    A, b = A[good], intensity[good]
    if A.shape[0] < A.shape[1] + 1:
        return {"error": "Too little overlap between spectrum and references."}
    coeffs, resid = nnls(A, b)
    total = float(coeffs.sum())
    fractions = (coeffs / total).tolist() if total > 0 else coeffs.tolist()
    ss_res = float(np.sum((A @ coeffs - b) ** 2))
    ss_tot = float(np.sum((b - b.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else None
    return {
        "components": [{"name": n, "fraction": round(f, 4), "raw_weight": round(float(c), 6)}
                       for n, f, c in zip(names, fractions, coeffs)],
        "fit_r2": round(r2, 4) if r2 is not None else None,
        "residual_norm": round(float(resid), 6),
        "n_points_used": int(A.shape[0]),
    }
