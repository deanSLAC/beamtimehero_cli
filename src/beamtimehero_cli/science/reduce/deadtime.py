"""Detector deadtime correction (ICR-based, non-paralyzable)."""
from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Detector deadtime correction (ICR-based, non-paralyzable)
# ---------------------------------------------------------------------------

def deadtime_correct(
    sca: np.ndarray, icr: np.ndarray, count_time: np.ndarray, tau: float,
) -> np.ndarray:
    """Non-paralyzable per-element deadtime correction for windowed counts.

    corrected = sca / (1 − tau · ICR/count_time), clipped so a pathological
    ICR cannot flip the sign or blow up the correction (floor at 5% live).

    The ``vortDT*`` counters at BL 15-2 are already deadtime-corrected by
    the DXP hardware — do NOT run this on them. It exists for detectors
    whose raw windowed counts and incoming count rates are recorded
    separately (e.g. the SSRL BL 4-3 Xspress3 ``SCA1_n``/``ICR1_n``
    columns).

    Parameters
    ----------
    sca : (npts, nelem) windowed counts per element
    icr : (npts, nelem) incoming counts per element (same integration)
    count_time : (npts,) integration time in seconds
    tau : per-event dead time in seconds
    """
    sca = np.asarray(sca, dtype=float)
    icr = np.asarray(icr, dtype=float)
    count_time = np.asarray(count_time, dtype=float)
    rate = icr / np.maximum(count_time[:, np.newaxis], 1e-9)
    live = np.clip(1.0 - float(tau) * rate, 0.05, 1.0)
    return sca / live

# ---------------------------------------------------------------------------
# CITATIONS — method -> reference. ``None`` means the method is implemented
# but not yet attributed; those surface as gaps on the generated science
# index, and filling one in is a welcome contribution. See science/README.md.
# ---------------------------------------------------------------------------

CITATIONS = {
    "Non-paralyzable deadtime correction": (
        "corrected = sca / (1 - tau * ICR/count_time), the standard "
        "non-paralyzable model, clipped at 5% live time."
    ),
}
