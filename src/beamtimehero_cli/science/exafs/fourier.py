"""Fourier transform of chi(k) into R space, and first-shell peak reporting."""
from __future__ import annotations

import numpy as np

from beamtimehero_cli.science.exafs.kspace import rebin_k
from beamtimehero_cli.science.exafs.policy import (
    DEFAULT_DK,
    DEFAULT_KMAX,
    DEFAULT_KMIN,
    DEFAULT_KWEIGHT,
)


# ---------------------------------------------------------------------------
# Fourier transform to R-space
# ---------------------------------------------------------------------------

def ft_window(
    k: np.ndarray, kmin: float, kmax: float, dk: float = DEFAULT_DK,
    kind: str = "hanning",
) -> np.ndarray:
    """Hanning-sill FT window on grid ``k`` (sills of width ``dk`` centred
    on kmin/kmax). ``kind`` is recorded by callers; only hanning sills are
    implemented."""
    if kind != "hanning":
        raise ValueError(f"Unsupported window kind '{kind}' (only 'hanning').")
    k = np.asarray(k, dtype=float)
    win = np.zeros_like(k)
    win[(k >= kmin) & (k <= kmax)] = 1.0
    lo = (k >= kmin - dk / 2) & (k < kmin + dk / 2)
    hi = (k > kmax - dk / 2) & (k <= kmax + dk / 2)
    win[lo] = np.sin(np.pi / 2 * (k[lo] - (kmin - dk / 2)) / dk) ** 2
    win[hi] = np.cos(np.pi / 2 * (k[hi] - (kmax - dk / 2)) / dk) ** 2
    return win


def xftf(
    k: np.ndarray,
    chi: np.ndarray,
    kmin: float = DEFAULT_KMIN,
    kmax: float | None = DEFAULT_KMAX,
    kweight: int = DEFAULT_KWEIGHT,
    dk: float = DEFAULT_DK,
    nfft: int = 2048,
    kstep: float = 0.05,
    rmax_out: float = 10.0,
) -> dict:
    """Forward FT chi(k) → chi(R), Ifeffit convention.

    chi(R) = (kstep/√π) · FFT[chi · k^kweight · window]. Returns
    ``{r, chir_mag, chir_re, chir_im, provenance}`` truncated to
    ``r <= rmax_out``. The R axis is **phase-uncorrected**: first-shell
    peaks sit ~0.3–0.5 Å below the true bond length.
    """
    kg, cg = rebin_k(k, chi, kstep=kstep)
    if kmax is None:
        kmax = float(kg.max()) - 0.5
    win = ft_window(kg, kmin, kmax, dk)
    arr = np.zeros(nfft, dtype=complex)
    arr[: len(kg)] = cg * kg**kweight * win
    ft = np.fft.fft(arr)[: nfft // 2] * kstep / np.sqrt(np.pi)
    r = np.pi * np.arange(nfft // 2) / (nfft * kstep)
    sel = r <= rmax_out
    return {
        "r": r[sel],
        "chir_mag": np.abs(ft)[sel],
        "chir_re": ft.real[sel],
        "chir_im": ft.imag[sel],
        "provenance": {
            "method": "xftf",
            "convention": "Ifeffit: chi(R) = (kstep/sqrt(pi)) * FFT[chi*k^w*win]",
            "window": "hanning",
            "kmin_inv_ang": float(kmin),
            "kmax_inv_ang": float(kmax),
            "dk_inv_ang": float(dk),
            "kweight": int(kweight),
            "kstep_inv_ang": float(kstep),
            "nfft": int(nfft),
            "r_axis": "phase-uncorrected (peaks ~0.3-0.5 Å below bond length)",
        },
    }


def first_shell_peak(
    r: np.ndarray, chir_mag: np.ndarray,
    rmin: float = 1.0, rmax: float = 4.0,
) -> dict:
    """Position/height of the largest |chi(R)| peak in [rmin, rmax].

    A descriptor, not a fit: parabola-refined argmax, honest about the
    phase-uncorrected axis. Returns ``{found: False}`` when the window is
    empty or holds no interior maximum.
    """
    r = np.asarray(r, dtype=float)
    mag = np.asarray(chir_mag, dtype=float)
    sel = (r >= rmin) & (r <= rmax)
    if int(sel.sum()) < 3:
        return {"found": False, "reason": f"fewer than 3 points in [{rmin}, {rmax}] Å"}
    rw, mw = r[sel], mag[sel]
    i = int(np.argmax(mw))
    peak_r, peak_h = float(rw[i]), float(mw[i])
    if 0 < i < len(rw) - 1:
        y0, y1, y2 = mw[i - 1], mw[i], mw[i + 1]
        denom = y0 - 2 * y1 + y2
        if denom < 0:
            step = float(rw[i + 1] - rw[i])
            peak_r = float(rw[i] + np.clip(0.5 * (y0 - y2) / denom, -1, 1) * step)
    return {
        "found": True,
        "r_peak_ang": peak_r,
        "height": peak_h,
        "window_ang": [float(rmin), float(rmax)],
        "caveat": (
            "Phase-uncorrected apparent distance; the physical bond length is "
            "~0.3-0.5 Å longer. Quantitative distances require FEFF path fitting."
        ),
    }

# ---------------------------------------------------------------------------
# CITATIONS — method -> reference. ``None`` means the method is implemented
# but not yet attributed; those surface as gaps on the generated science
# index, and filling one in is a welcome contribution. See science/README.md.
# ---------------------------------------------------------------------------

CITATIONS = {
    "chi(k) -> chi(R) Fourier transform convention": (
        "Ifeffit convention: chi(R) = (kstep/sqrt(pi)) * FFT[chi * k^w * window]."
    ),
    "Hanning-sill k-window": None,
    "First-shell peak reporting": None,
}
