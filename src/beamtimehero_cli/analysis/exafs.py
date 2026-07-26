"""EXAFS math — backend-agnostic.

Pure functions like ``analysis/xas.py``: arrays in, dicts/arrays out, no file
or DB I/O. This module supplies the k-space half of the XAS chain that the
XANES/HERFD modules deliberately do not cover:

    normalized mu(E) → background spline → chi(k) → k-weight → FT → |chi(R)|

Provenance discipline matches ``interpretation/normalize.py``: every derived
product carries a ``provenance`` dict naming the method and its parameters,
and ``autobk_lite`` declares itself a quick-look background (a reduced
AUTOBK: spline knots from the Nyquist criterion, no reference-channel or
FEFF-based refinement). For publication-grade backgrounds cross-check against
Larch/Athena; the FT itself matches the Ifeffit convention and needs no such
caveat.

Ported from the webxas-data prototype (py-analysis/exafs.py, validated on
SSRL BL 4-3 S K-edge k≈9.5 EXAFS and Ti K XANES, 2026-07).

Conventions: energies in eV, k in Å⁻¹, R in Å.
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import UnivariateSpline, interp1d

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


# ---------------------------------------------------------------------------
# Background removal → chi(k)
# ---------------------------------------------------------------------------

def autobk_lite(
    energy: np.ndarray,
    mu: np.ndarray,
    e0: float,
    edge_step: float = 1.0,
    rbkg: float = 1.0,
    kweight: int = 2,
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


def rebin_k(
    k: np.ndarray, chi: np.ndarray,
    kstep: float = 0.05, kmin: float = 0.0, kmax: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Interpolate chi onto a uniform k grid (required before the FFT)."""
    k = np.asarray(k, dtype=float)
    chi = np.asarray(chi, dtype=float)
    if kmax is None:
        kmax = float(k.max())
    grid = np.arange(kmin, kmax, kstep)
    f = interp1d(k, chi, bounds_error=False, fill_value=0.0)
    return grid, f(grid)


# ---------------------------------------------------------------------------
# Fourier transform to R-space
# ---------------------------------------------------------------------------

def ft_window(
    k: np.ndarray, kmin: float, kmax: float, dk: float = 1.0,
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
    kmin: float = 2.0,
    kmax: float | None = None,
    kweight: int = 2,
    dk: float = 1.0,
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
