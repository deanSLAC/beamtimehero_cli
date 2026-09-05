"""AUTOBK-lite background removal: mu(E) -> chi(k).

Spline knots from the Nyquist criterion, no reference-channel or standard
constraint.
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import UnivariateSpline

from beamtimehero_cli.science.exafs.kspace import etok
from beamtimehero_cli.science.exafs.policy import DEFAULT_KWEIGHT, DEFAULT_RBKG


# ---------------------------------------------------------------------------
# Background removal → chi(k)
# ---------------------------------------------------------------------------

def autobk_lite(
    energy: np.ndarray,
    mu: np.ndarray,
    e0: float,
    edge_step: float = 1.0,
    rbkg: float = DEFAULT_RBKG,
    kweight: int = DEFAULT_KWEIGHT,
) -> dict:
    """Quick-look AUTOBK: spline background above E0 → chi(k).

    The spline knot budget follows the AUTOBK Nyquist criterion
    (nknots ≈ 2·rbkg·kmax/π + 1) so background flexibility is capped at
    R < ``rbkg`` and structural oscillations above it survive. The fit is
    weighted by k^``kweight`` so the spline tracks the EXAFS mean at high k
    instead of chasing the white line.

    Returns ``{k, chi, bkg, nknots, provenance}`` — ``k``/``chi``/``bkg``
    are arrays on the (non-uniform) k grid of the input points at/above E0;
    rebin with :func:`rebin_k` before FT. Raises ValueError on degenerate
    input (fewer than ~10 points above the edge).
    """
    energy = np.asarray(energy, dtype=float)
    mu = np.asarray(mu, dtype=float)
    sel = energy >= float(e0)
    if int(sel.sum()) < 10:
        raise ValueError(
            f"Only {int(sel.sum())} points at/above E0={e0:.1f} eV — "
            "not enough for a background spline."
        )
    e, m = energy[sel], mu[sel]
    k = etok(e, e0)
    edge_step = float(edge_step) if edge_step else 1.0

    kmax = float(k.max())
    nknots = max(int(2 * rbkg * kmax / np.pi) + 1, 5)
    w = np.maximum(k, 0.1) ** kweight
    spline = UnivariateSpline(k, m, w=w, k=3)
    # binary-search the smoothing factor down to the knot budget
    lo, hi = 0.0, spline.get_residual() * 100 + 1.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        spline.set_smoothing_factor(mid)
        if len(spline.get_knots()) > nknots:
            lo = mid
        else:
            hi = mid
    bkg = spline(k)
    chi = (m - bkg) / edge_step
    return {
        "k": k,
        "chi": chi,
        "bkg": bkg,
        "nknots": int(len(spline.get_knots())),
        "provenance": {
            "method": "autobk_lite",
            "note": (
                "Reduced AUTOBK: cubic smoothing spline, knot budget from the "
                "Nyquist criterion (2·rbkg·kmax/π). Quick-look quality — "
                "cross-check against Larch/Ifeffit autobk for publication."
            ),
            "e0_ev": float(e0),
            "edge_step": edge_step,
            "rbkg_ang": float(rbkg),
            "spline_kweight": int(kweight),
            "kmax_inv_ang": kmax,
        },
    }

# ---------------------------------------------------------------------------
# CITATIONS — method -> reference. ``None`` means the method is implemented
# but not yet attributed; those surface as gaps on the generated science
# index, and filling one in is a welcome contribution. See science/README.md.
# ---------------------------------------------------------------------------

CITATIONS = {
    "AUTOBK-lite spline background removal": (
        "Reduced AUTOBK — cubic smoothing spline with the knot budget from "
        "the Nyquist criterion (2*rbkg*kmax/pi). Quick-look quality; "
        "cross-check against Larch/Ifeffit autobk before publication."
    ),
}
