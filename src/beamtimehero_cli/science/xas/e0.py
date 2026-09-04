"""Edge position E0 and core-hole re-broadening.

``find_e0`` locates the absorption edge as the parabola-refined maximum of
the Savitzky-Golay smoothed first derivative. ``rebroaden`` convolves a HERFD
spectrum with the tabulated core-hole width so conventional-XANES
calibrations apply validly to it.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import savgol_filter


E0_DEFINITION = "derivative_max (Savitzky-Golay smoothed, parabola-refined)"

# ---------------------------------------------------------------------------
# Grid helpers
# ---------------------------------------------------------------------------

def _uniform(energy: np.ndarray, mu: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Interpolate onto a uniform grid (median step) for filters/convolution."""
    energy = np.asarray(energy, dtype=float)
    mu = np.asarray(mu, dtype=float)
    step = float(np.median(np.diff(energy)))
    if step <= 0:
        raise ValueError("Energy axis must be strictly increasing.")
    e_u = np.arange(energy[0], energy[-1] + step / 2, step)
    return e_u, np.interp(e_u, energy, mu), step


def _odd_window_points(step: float, span_ev: float, n: int) -> int:
    pts = max(5, int(round(span_ev / step)) | 1)
    return min(pts, (n - 1) | 1 if (n - 1) % 2 else (n - 2) | 1)


# ---------------------------------------------------------------------------
# E0
# ---------------------------------------------------------------------------

def find_e0(energy: np.ndarray, mu: np.ndarray, smooth_span_ev: float = 2.0) -> dict:
    """Edge position under both fixed definitions, with uncertainty.

    The derivative-max uncertainty combines the grid half-step floor with
    the parabola-refinement curvature; it does NOT include the energy-
    calibration systematic (that lives in the calibration record).
    """
    e_u, mu_u, step = _uniform(energy, mu)
    window = _odd_window_points(step, smooth_span_ev, len(e_u))
    deriv = savgol_filter(mu_u, window_length=window, polyorder=2, deriv=1, delta=step)
    i = int(np.argmax(deriv))

    e0 = float(e_u[i])
    unc = step / 2.0
    if 0 < i < len(e_u) - 1:
        y0, y1, y2 = deriv[i - 1], deriv[i], deriv[i + 1]
        denom = y0 - 2 * y1 + y2
        if denom < 0:  # proper maximum
            shift = 0.5 * (y0 - y2) / denom
            e0 = float(e_u[i] + np.clip(shift, -1, 1) * step)

    # half-step: first upward 0.5-crossing within a few smoothing spans of e0
    e0_half = None
    near = (e_u > e0 - 5 * smooth_span_ev) & (e_u < e0 + 5 * smooth_span_ev)
    idx = np.where(near & (mu_u >= 0.5))[0]
    if len(idx) and idx[0] > 0:
        j = idx[0]
        y_lo, y_hi = mu_u[j - 1], mu_u[j]
        if y_hi > y_lo:
            e0_half = float(e_u[j - 1] + (0.5 - y_lo) / (y_hi - y_lo) * step)

    return {
        "e0_ev": e0,
        "e0_unc_ev": float(unc),
        "e0_definition": E0_DEFINITION,
        "e0_half_step_ev": e0_half,
        "grid_step_ev": step,
        "smooth_span_ev": smooth_span_ev,
    }


# ---------------------------------------------------------------------------
# Core-hole re-broadening (HERFD -> conventional calibration domain)
# ---------------------------------------------------------------------------

def rebroaden(energy: np.ndarray, mu: np.ndarray, fwhm_ev: float) -> np.ndarray:
    """Convolve a HERFD spectrum with a Lorentzian of the core-hole width.

    Puts lifetime-sharpened HERFD data on the same footing as
    conventional-XANES calibrations (e.g. Wilke 2001) before those
    calibrations are applied. Returns mu on the input grid.
    """
    if fwhm_ev <= 0:
        return np.asarray(mu, dtype=float)
    e_u, mu_u, step = _uniform(energy, mu)
    hwhm = fwhm_ev / 2.0
    k = int(np.ceil(40 * hwhm / step))
    x = np.arange(-k, k + 1) * step
    kernel = hwhm / (np.pi * (x**2 + hwhm**2))
    kernel /= kernel.sum()
    padded = np.concatenate([np.full(k, mu_u[0]), mu_u, np.full(k, mu_u[-1])])
    broadened = np.convolve(padded, kernel, mode="same")[k:-k]
    return np.interp(energy, e_u, broadened)
