"""Numeric descriptors from a reduced XRS edge (energy-loss axis).

Backend-agnostic like ``analysis/xas.py`` and ``interpretation/descriptors.py``:
arrays in, dicts out, no I/O. Operates on a background-subtracted, averaged XRS
edge (loss vs intensity). The measurable features that drive XRS interpretation:

- edge onset (inflection of the rising edge on the loss axis),
- pre-edge peak (position + integrated area — the O-K / metal probe of covalency
  and oxygen redox),
- white line / main peak (position + height),
- integrated edge area (for area normalization / comparison),
- SNR of the edge feature (amplitude above post-edge vs post-edge noise).
"""
from __future__ import annotations

import numpy as np
from scipy.signal import savgol_filter


def _uniform(loss, intensity):
    loss = np.asarray(loss, dtype=float)
    intensity = np.asarray(intensity, dtype=float)
    ok = np.isfinite(loss) & np.isfinite(intensity)
    loss, intensity = loss[ok], intensity[ok]
    order = np.argsort(loss)
    loss, intensity = loss[order], intensity[order]
    step = float(np.median(np.diff(loss))) if loss.size > 1 else 1.0
    if step <= 0:
        raise ValueError("Loss axis must be increasing.")
    grid = np.arange(loss[0], loss[-1] + step / 2, step)
    return grid, np.interp(grid, loss, intensity), step


def edge_onset(loss, intensity, smooth_span_ev: float = 2.0) -> dict:
    """Energy-loss of the maximum rising-edge slope (edge position proxy).

    Savitzky-Golay first derivative, parabola-refined at the argmax — the loss
    analogue of ``find_e0`` but computed on the XRS loss axis (only valid after
    Compton subtraction; on a raw spectrum the Compton rise dominates).
    """
    grid, y, step = _uniform(loss, intensity)
    win = max(5, int(round(smooth_span_ev / step)) | 1)
    win = min(win, (len(grid) - 1) | 1 if (len(grid) - 1) % 2 else (len(grid) - 2) | 1)
    if win < 5 or len(grid) < 7:
        i = int(np.argmax(np.gradient(y, grid)))
        return {"onset_loss_ev": float(grid[i]), "method": "gradient_argmax",
                "grid_step_ev": step}
    deriv = savgol_filter(y, window_length=win, polyorder=2, deriv=1, delta=step)
    i = int(np.argmax(deriv))
    onset = float(grid[i])
    if 0 < i < len(grid) - 1:
        y0, y1, y2 = deriv[i - 1], deriv[i], deriv[i + 1]
        denom = y0 - 2 * y1 + y2
        if denom < 0:
            onset = float(grid[i] + np.clip(0.5 * (y0 - y2) / denom, -1, 1) * step)
    return {"onset_loss_ev": onset, "onset_unc_ev": step / 2.0,
            "method": "savgol_derivative_max", "grid_step_ev": step}


def _window(loss, intensity, lo, hi):
    loss = np.asarray(loss, dtype=float)
    intensity = np.asarray(intensity, dtype=float)
    m = np.isfinite(intensity) & (loss >= lo) & (loss <= hi)
    return loss[m], intensity[m]


def peak_in_window(loss, intensity, lo, hi) -> dict:
    """Position + height of the maximum in a loss window (white line / pre-edge)."""
    x, y = _window(loss, intensity, lo, hi)
    if x.size == 0:
        return {"found": False}
    i = int(np.argmax(y))
    return {"found": True, "peak_loss_ev": float(x[i]), "peak_height": float(y[i]),
            "window_ev": [lo, hi]}


def integrated_area(loss, intensity, lo, hi) -> float:
    """Trapezoidal integral of intensity over [lo, hi] on the loss axis."""
    x, y = _window(loss, intensity, lo, hi)
    if x.size < 2:
        return 0.0
    trapz = getattr(np, "trapezoid", None) or np.trapz
    return float(trapz(y, x))


def feature_snr(loss, intensity, edge_lo, edge_hi) -> dict:
    """SNR of the edge feature: peak amplitude above the post-edge / post-edge noise.

    Post-edge noise is the trend-robust DER_SNR estimate over the region above
    ``edge_hi``. This is the XRS analogue of scoring the feature window, not the
    whole spectrum (which the Compton background dominates).
    """
    loss = np.asarray(loss, dtype=float)
    intensity = np.asarray(intensity, dtype=float)
    x, y = _window(loss, intensity, edge_lo, edge_hi)
    post = intensity[np.isfinite(intensity) & (loss > edge_hi)]
    if x.size == 0:
        return {"snr": None, "reason": "empty edge window"}
    amp = max(0.0, float(np.max(y) - (np.median(post) if post.size else np.median(y))))
    if post.size >= 5:
        noise = 1.482602 / np.sqrt(6.0) * float(
            np.median(np.abs(2.0 * post[2:-2] - post[:-4] - post[4:])))
    else:
        noise = float(np.std(post)) if post.size > 1 else 0.0
    snr = amp / noise if noise > 0 else None
    return {"snr": round(snr, 2) if snr is not None else None,
            "edge_amplitude": amp, "post_edge_noise": noise}


def extract_xrs_descriptors(
    loss, intensity, edge_info: dict | None = None,
    edge_window=None, pre_edge_window=None,
) -> tuple[dict, dict]:
    """Full XRS descriptor extraction. Returns ``(descriptors, arrays)``.

    ``edge_window`` (loss eV) bounds the edge/white-line region; if omitted it is
    taken as [onset−5, onset+35]. ``pre_edge_window`` bounds the pre-edge feature
    (e.g. the O-K pre-edge / metal pre-edge); if omitted, [onset−8, onset+2].
    Intended for a background-subtracted spectrum.
    """
    loss = np.asarray(loss, dtype=float)
    intensity = np.asarray(intensity, dtype=float)
    flags = []

    onset = edge_onset(loss, intensity)
    o = onset["onset_loss_ev"]
    if edge_window is None:
        edge_window = (o - 5.0, o + 35.0)
    if pre_edge_window is None:
        pre_edge_window = (o - 8.0, o + 2.0)

    white_line = peak_in_window(loss, intensity, *edge_window)
    pre_edge = peak_in_window(loss, intensity, *pre_edge_window)
    edge_area = integrated_area(loss, intensity, *edge_window)
    pre_area = integrated_area(loss, intensity, *pre_edge_window)
    snr = feature_snr(loss, intensity, *edge_window)

    pre_frac = (pre_area / edge_area) if edge_area else None
    if snr.get("snr") is not None and snr["snr"] < 3:
        flags.append("low_feature_snr")

    descriptors = {
        "edge": edge_info,
        "onset": onset,
        "white_line": white_line,
        "pre_edge": pre_edge,
        "edge_area": edge_area,
        "pre_edge_area": pre_area,
        "pre_edge_fraction": pre_frac,
        "feature_snr": snr,
        "windows": {"edge": list(edge_window), "pre_edge": list(pre_edge_window)},
        "flags": flags,
        "axis": "energy_loss_ev",
    }
    arrays = {"loss": loss, "intensity": intensity}
    return descriptors, arrays
