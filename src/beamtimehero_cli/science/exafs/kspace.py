"""Energy <-> photoelectron wavenumber conversion, and k-grid rebinning."""
from __future__ import annotations

import numpy as np
from scipy.interpolate import interp1d


# hbar^2/2m_e in eV·Å²: k = sqrt((E-E0)/ETOK)
ETOK = 3.8099821161548593


# ---------------------------------------------------------------------------
# Axis conversion
# ---------------------------------------------------------------------------

def etok(energy: np.ndarray, e0: float) -> np.ndarray:
    """Photoelectron wavenumber k (Å⁻¹) for energies at/above e0.

    Energies below e0 map to k=0 (clipped, not complex).
    """
    energy = np.asarray(energy, dtype=float)
    return np.sqrt(np.maximum(energy - float(e0), 0.0) / ETOK)


def ktoe(k: np.ndarray, e0: float) -> np.ndarray:
    """Inverse of :func:`etok`: absolute energy (eV) for wavenumber k."""
    k = np.asarray(k, dtype=float)
    return float(e0) + ETOK * k**2

def rebin_k(
    k: np.ndarray, chi: np.ndarray,
    kstep: float = 0.05, kmin: float = 0.0, kmax: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Interpolate chi onto a uniform k grid (required before the FFT).

    ``kmin`` here is a *regrid floor*, not the FT window bound — it is
    deliberately 0.0 and NOT ``policy.DEFAULT_KMIN``. Rebinning keeps the full
    measured range; the k range that actually enters the transform is applied
    later by the window in :func:`.fourier.ft_window`. Raising it here would
    silently discard low-k data before windowing.
    """
    k = np.asarray(k, dtype=float)
    chi = np.asarray(chi, dtype=float)
    if kmax is None:
        kmax = float(k.max())
    grid = np.arange(kmin, kmax, kstep)
    f = interp1d(k, chi, bounds_error=False, fill_value=0.0)
    return grid, f(grid)

# ---------------------------------------------------------------------------
# CITATIONS — method -> reference. ``None`` means the method is implemented
# but not yet attributed; those surface as gaps on the generated science
# index, and filling one in is a welcome contribution. See science/README.md.
# ---------------------------------------------------------------------------

CITATIONS = {
    "Energy <-> photoelectron wavenumber": (
        "k = sqrt((E - E0) / ETOK) with ETOK = hbar^2/2m_e = 3.8099821 eV*A^2."
    ),
}
