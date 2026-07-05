"""X-ray Raman scattering (XRS / non-resonant inelastic X-ray scattering) math.

Backend-agnostic and pure, like ``analysis/xas.py``: arrays in, arrays/dicts
out, no file or DB I/O. This is the processing core for the XRS pipeline; the
CLI tools in ``tool_catalog`` load scans and call these functions.

Why XRS needs its own module (see ``beamtimehero ref counter-selection`` and
``docs/xrs-analysis-branch-plan.md``):

- XRS measures the dynamic structure factor S(q,ω) on an **energy-loss axis**
  (loss = incident mono energy − fixed analyzer energy), not an absorption
  coefficient. The near-edge feature is a **weak bump on a large sloping
  Compton background** — there is no absorption edge step.
- Therefore edge-step normalization (``analysis.xas.edge_step_normalize``) is
  wrong here, and repeated scans must be aligned on the **elastic (Rayleigh)
  line**, not on the max-derivative edge.

The reduction chain implemented here:
  elastic-line calibration → energy-loss axis → (per-crystal alignment + sum
  with outlier rejection) → Compton background subtraction → area/absolute
  normalization; plus momentum transfer q from the scattering angle 2θ.

References: Sahle et al., J. Synchrotron Rad. 22, 400 (2015); Sokaras et al.,
Rev. Sci. Instrum. 83, 043112 (2012) (SSRL BL6-2); the ESRF XRStools package.
"""
from __future__ import annotations

import numpy as np

# hc in eV·Å — converts photon energy to wavelength: lambda[Å] = _HC_EV_ANG / E[eV]
_HC_EV_ANG = 12398.419843320026

# numpy 2.x renamed trapz -> trapezoid; support both.
_trapz = getattr(np, "trapezoid", None) or np.trapz


# ---------------------------------------------------------------------------
# Momentum transfer
# ---------------------------------------------------------------------------

def q_from_two_theta(incident_energy_ev: float, two_theta_deg: float) -> float:
    """Momentum transfer |q| in Å⁻¹ for elastic-limit XRS.

    q = (4π/λ)·sin(θ), θ = 2θ/2, λ[Å] = hc/E. Valid because core energy losses
    (tens–hundreds of eV) are ≪ the ~10 keV photon energy, so |k_in| ≈ |k_out|.
    Low q → dipole (XANES-like); high q → monopole/quadrupole turn on.
    """
    e = float(incident_energy_ev)
    if e <= 0:
        raise ValueError("incident_energy_ev must be positive.")
    lam = _HC_EV_ANG / e
    theta = np.radians(float(two_theta_deg) / 2.0)
    return float(4.0 * np.pi * np.sin(theta) / lam)


# ---------------------------------------------------------------------------
# Elastic-line calibration (the loss-axis anchor; replaces find_e0 for XRS)
# ---------------------------------------------------------------------------

def fit_elastic_line(energy: np.ndarray, intensity: np.ndarray) -> dict:
    """Locate the elastic (Rayleigh) peak: ω=0 anchor and energy resolution.

    Returns ``{elastic_center_ev, resolution_fwhm_ev, amplitude, method,
    fit_ok}``. A Gaussian fit is attempted first (peak center + FWHM =
    2.3548·σ); on failure it falls back to the center-of-mass near the maximum
    and a half-maximum width. The center defines the zero of energy loss; the
    FWHM is the instrumental energy resolution.
    """
    energy = np.asarray(energy, dtype=float)
    intensity = np.asarray(intensity, dtype=float)
    if energy.size < 3:
        raise ValueError("Need at least 3 points to fit an elastic line.")

    baseline = float(np.median(intensity))
    net = intensity - baseline
    i_max = int(np.argmax(net))
    center_guess = float(energy[i_max])

    try:
        from lmfit.models import GaussianModel, ConstantModel

        model = GaussianModel() + ConstantModel()
        span = energy.max() - energy.min()
        pars = model.make_params(
            amplitude=float(max(net[i_max], 1e-9)) * (span / 20 + 1e-9),
            center=center_guess,
            sigma=max(span / 20.0, 1e-6),
            c=baseline,
        )
        out = model.fit(intensity, pars, x=energy)
        center = float(out.params["center"].value)
        sigma = abs(float(out.params["sigma"].value))
        fwhm = 2.0 * np.sqrt(2.0 * np.log(2.0)) * sigma
        amp = float(out.params["amplitude"].value)
        if energy.min() <= center <= energy.max() and fwhm > 0:
            return {
                "elastic_center_ev": center,
                "resolution_fwhm_ev": fwhm,
                "amplitude": amp,
                "method": "gaussian_fit",
                "fit_ok": True,
            }
    except Exception:
        pass

    # Fallback: center-of-mass over points above half-max, half-max width.
    peak = float(np.max(net))
    if peak <= 0:
        return {
            "elastic_center_ev": center_guess,
            "resolution_fwhm_ev": None,
            "amplitude": 0.0,
            "method": "argmax_no_peak",
            "fit_ok": False,
        }
    mask = net >= 0.5 * peak
    com = float(np.sum(energy[mask] * net[mask]) / np.sum(net[mask]))
    width = float(energy[mask].max() - energy[mask].min()) if mask.sum() > 1 else None
    return {
        "elastic_center_ev": com,
        "resolution_fwhm_ev": width,
        "amplitude": peak,
        "method": "center_of_mass_fallback",
        "fit_ok": True,
    }


def to_energy_loss(energy_ev: np.ndarray, elastic_center_ev: float) -> np.ndarray:
    """Convert an incident-energy axis to energy loss ω = E − E_elastic (eV)."""
    return np.asarray(energy_ev, dtype=float) - float(elastic_center_ev)


# ---------------------------------------------------------------------------
# Grid alignment and rep averaging (photon-starved: many short scans summed)
# ---------------------------------------------------------------------------

def common_loss_grid(loss_arrays, step: float | None = None) -> np.ndarray:
    """Build a common energy-loss grid spanning the overlap of all inputs.

    Uses the median point spacing across inputs unless ``step`` is given. The
    grid is the intersection [max of mins, min of maxes] so every input covers
    every grid point (no extrapolation).
    """
    los = [np.asarray(a, dtype=float) for a in loss_arrays if len(a) > 1]
    if not los:
        raise ValueError("No usable loss arrays.")
    lo = max(float(a.min()) for a in los)
    hi = min(float(a.max()) for a in los)
    if not (hi > lo):
        raise ValueError("Loss arrays do not overlap on a common range.")
    if step is None:
        step = float(np.median([np.median(np.diff(a)) for a in los]))
    if step <= 0:
        raise ValueError("Non-positive grid step.")
    n = max(2, int(round((hi - lo) / step)) + 1)
    return np.linspace(lo, hi, n)


def align_and_average(
    loss_arrays, intensity_arrays, grid: np.ndarray | None = None,
) -> dict:
    """Interpolate reps onto a common loss grid and average them.

    Each rep is expected already re-referenced to its own elastic line (so the
    loss axes agree). Returns ``{loss, mean, sem, std, n_reps}`` as numpy
    arrays. SEM = std / sqrt(n) — the propagated uncertainty on the mean.
    """
    loss_arrays = [np.asarray(a, dtype=float) for a in loss_arrays]
    intensity_arrays = [np.asarray(a, dtype=float) for a in intensity_arrays]
    if len(loss_arrays) != len(intensity_arrays) or not loss_arrays:
        raise ValueError("Need matching, non-empty loss/intensity arrays.")
    if grid is None:
        grid = common_loss_grid(loss_arrays)
    stack = np.vstack([
        np.interp(grid, lo, inten, left=np.nan, right=np.nan)
        for lo, inten in zip(loss_arrays, intensity_arrays)
    ])
    n = stack.shape[0]
    mean = np.nanmean(stack, axis=0)
    std = np.nanstd(stack, axis=0, ddof=1) if n > 1 else np.zeros_like(mean)
    sem = std / np.sqrt(n) if n > 1 else np.zeros_like(mean)
    return {"loss": grid, "mean": mean, "sem": sem, "std": std, "n_reps": n}


# ---------------------------------------------------------------------------
# Multi-analyzer / multi-crystal: align, reject outliers, sum
# ---------------------------------------------------------------------------

def _der_snr(values: np.ndarray) -> float:
    """Robust SNR insensitive to smooth trends (Stoehr et al. 2008, DER_SNR).

    Noise from the median of |2y_i − y_{i-2} − y_{i+2}|, which cancels a linear
    slope, so a genuinely sloping Compton background isn't mistaken for noise.
    Signal amplitude is the peak-above-median. Returns +inf for a noiseless
    channel, 0 for a flat/degenerate one.
    """
    v = values[np.isfinite(values)]
    if v.size < 5:
        return float("inf")
    noise = 1.482602 / np.sqrt(6.0) * np.median(np.abs(2.0 * v[2:-2] - v[:-4] - v[4:]))
    amp = float(np.max(v) - np.median(v))
    if noise <= 0:
        return float("inf") if amp > 0 else 0.0
    return float(amp / noise)


def reject_outlier_channels(
    grid: np.ndarray, channel_intensities, snr_min: float = 2.0,
    dev_mad_max: float = 4.0,
) -> dict:
    """Flag crystal/ROI channels to drop before summing.

    Each channel has already been interpolated onto a common loss grid. A
    channel is rejected when (a) its peak-to-noise SNR (trend-robust DER_SNR)
    is below ``snr_min``, or (b) its area-normalized shape sits more than
    ``dev_mad_max`` robust sigmas away from the *cross-channel* spread of
    shape-deviations (so a lone bad channel is rejected, not the pack). Scale
    differences alone never reject — the comparison is area-normalized.
    Returns ``{keep: [bool], reasons: [str|None], per_channel: [...]}``.
    """
    chans = [np.asarray(c, dtype=float) for c in channel_intensities]
    n = len(chans)
    if n == 0:
        return {"keep": [], "reasons": [], "per_channel": []}

    def _area_norm(c):
        area = np.nansum(np.abs(c))
        return c / area if area > 0 else c

    normed = np.vstack([_area_norm(c) for c in chans])
    median_shape = np.nanmedian(normed, axis=0)
    # Per-channel RMS deviation from the channel-median shape.
    devs = np.array([
        float(np.sqrt(np.nanmean((normed[i] - median_shape) ** 2))) for i in range(n)
    ])
    dev_med = float(np.median(devs))
    dev_mad = float(np.median(np.abs(devs - dev_med)))
    # Floor the scale at half the median deviation so that when every channel
    # agrees (MAD ≈ 0) a tiny numerical difference isn't amplified into a
    # spurious rejection — only a channel several× the typical deviation trips.
    dev_scale = max(1.4826 * dev_mad, 0.5 * dev_med, 1e-30)
    snrs = [_der_snr(c) for c in chans]

    keep, reasons, per = [], [], []
    for i in range(n):
        dev_sigma = (devs[i] - dev_med) / dev_scale
        reason = None
        if snrs[i] < snr_min:
            reason = f"low SNR ({snrs[i]:.1f} < {snr_min})"
        elif n >= 3 and dev_sigma > dev_mad_max:
            reason = f"shape deviates {dev_sigma:.1f}σ from the channel pack"
        keep.append(reason is None)
        reasons.append(reason)
        per.append({
            "channel_index": i,
            "snr": round(snrs[i], 2) if np.isfinite(snrs[i]) else None,
            "shape_deviation_sigma": round(float(dev_sigma), 2),
            "kept": reason is None,
        })
    return {"keep": keep, "reasons": reasons, "per_channel": per}


def sum_crystals(
    loss_arrays, channel_intensities, elastic_centers=None, reject: bool = True,
    grid: np.ndarray | None = None,
) -> dict:
    """Energy-align per-crystal spectra, reject outliers, and sum.

    The analyzer array Bragg-focuses onto the SDD and the SDD ROI gates the
    signal — they work together, so each crystal/ROI channel carries its own
    slightly different calibration and must be aligned on its own elastic line
    before co-adding. ``elastic_centers`` (one per channel) sets each channel's
    ω=0; if omitted the loss arrays are assumed already referenced.

    Returns ``{loss, summed, n_channels_used, n_channels_total, rejection}``.
    """
    loss_arrays = [np.asarray(a, dtype=float) for a in loss_arrays]
    channel_intensities = [np.asarray(a, dtype=float) for a in channel_intensities]
    if elastic_centers is not None:
        loss_arrays = [lo - float(c) for lo, c in zip(loss_arrays, elastic_centers)]
    if grid is None:
        grid = common_loss_grid(loss_arrays)
    on_grid = [np.interp(grid, lo, inten, left=np.nan, right=np.nan)
               for lo, inten in zip(loss_arrays, channel_intensities)]

    if reject and len(on_grid) >= 2:
        rej = reject_outlier_channels(grid, on_grid)
        kept = [c for c, k in zip(on_grid, rej["keep"]) if k]
        rejection = rej
    else:
        kept = on_grid
        rejection = {"keep": [True] * len(on_grid), "reasons": [None] * len(on_grid),
                     "per_channel": []}
    if not kept:
        raise ValueError("All crystal channels were rejected; none left to sum.")
    summed = np.nansum(np.vstack(kept), axis=0)
    return {
        "loss": grid,
        "summed": summed,
        "n_channels_used": len(kept),
        "n_channels_total": len(on_grid),
        "rejection": rejection,
    }


# ---------------------------------------------------------------------------
# Compton background subtraction (replaces the XAS pre/post polynomial)
# ---------------------------------------------------------------------------

BACKGROUND_MODELS = ("constant", "linear", "pearson7")


def subtract_compton_background(
    loss: np.ndarray, intensity: np.ndarray, edge_lo: float, edge_hi: float,
    model: str = "linear",
) -> dict:
    """Fit and subtract the Compton/valence background under the XRS edge.

    The background is fit ONLY to the flank points outside the edge window
    ``[edge_lo, edge_hi]`` (loss units), then evaluated across the full grid and
    subtracted. This is the XRS replacement for the XAS pre-edge line /
    post-edge polynomial: the physical baseline is the broad, sloping Compton
    profile, not a step.

    Models: ``constant`` (mean of the pre-edge flank), ``linear`` (line through
    both flanks), ``pearson7`` (Pearson VII through the flanks — the shape of the
    Compton hump; falls back to linear if the fit fails).

    Returns ``{loss, background, subtracted, model, n_flank_points, provenance}``.
    """
    if model not in BACKGROUND_MODELS:
        raise ValueError(f"Unknown model '{model}'. Use one of {list(BACKGROUND_MODELS)}.")
    loss = np.asarray(loss, dtype=float)
    intensity = np.asarray(intensity, dtype=float)
    if edge_lo >= edge_hi:
        raise ValueError("edge_lo must be < edge_hi.")

    flank = (loss < edge_lo) | (loss > edge_hi)
    finite = np.isfinite(intensity)
    fit_mask = flank & finite
    n_flank = int(fit_mask.sum())
    used_model = model
    if n_flank < 2:
        raise ValueError(
            f"Only {n_flank} background points outside [{edge_lo}, {edge_hi}] — "
            "widen the loss range or narrow the edge window."
        )

    xf, yf = loss[fit_mask], intensity[fit_mask]

    if model == "constant":
        pre = loss[fit_mask] < edge_lo
        level = float(np.mean(yf[pre])) if pre.any() else float(np.mean(yf))
        background = np.full_like(loss, level, dtype=float)
    elif model == "pearson7":
        background = None
        try:
            from lmfit.models import Pearson7Model, LinearModel

            mod = Pearson7Model(prefix="p_") + LinearModel(prefix="l_")
            pars = mod.make_params(
                p_amplitude=float(np.nanmax(yf) - np.nanmin(yf) + 1e-9),
                p_center=float(loss[np.nanargmax(np.where(finite, intensity, np.nan))]),
                p_sigma=float((loss.max() - loss.min()) / 2 + 1e-9),
                p_expon=2.0,
                l_slope=0.0, l_intercept=float(np.nanmin(yf)),
            )
            out = mod.fit(yf, pars, x=xf)
            background = out.eval(x=loss)
        except Exception:
            used_model = "linear"
        if background is None:
            coeffs = np.polyfit(xf, yf, 1)
            background = np.polyval(coeffs, loss)
    else:  # linear
        coeffs = np.polyfit(xf, yf, 1)
        background = np.polyval(coeffs, loss)

    subtracted = intensity - background
    return {
        "loss": loss,
        "background": np.asarray(background, dtype=float),
        "subtracted": subtracted,
        "model": used_model,
        "requested_model": model,
        "n_flank_points": n_flank,
        "edge_window": [edge_lo, edge_hi],
        "provenance": (
            "Compton/valence background fit to flank points outside the edge "
            "window and subtracted; the XRS replacement for XAS edge-step "
            "normalization (Sahle 2015 §5)."
        ),
    }


# ---------------------------------------------------------------------------
# XRS normalization (area / edge-jump — NOT edge-step)
# ---------------------------------------------------------------------------

def area_normalize(
    loss: np.ndarray, intensity: np.ndarray, lo: float | None = None,
    hi: float | None = None,
) -> dict:
    """Normalize an XRS spectrum to unit area over a loss window.

    The standard core-loss / EELS-like normalization when absolute (f-sum)
    units aren't available: divide by the trapezoidal integral over
    ``[lo, hi]`` (full range if unset). Returns ``{loss, normalized, area}``.
    """
    loss = np.asarray(loss, dtype=float)
    intensity = np.asarray(intensity, dtype=float)
    mask = np.isfinite(intensity)
    if lo is not None and hi is not None:
        mask &= (loss >= lo) & (loss <= hi)
    if mask.sum() < 2:
        raise ValueError("Not enough finite points in the normalization window.")
    area = float(_trapz(intensity[mask], loss[mask]))
    if abs(area) < 1e-30:
        raise ValueError("Integrated area is ~0; cannot area-normalize.")
    return {"loss": loss, "normalized": intensity / area, "area": area}
