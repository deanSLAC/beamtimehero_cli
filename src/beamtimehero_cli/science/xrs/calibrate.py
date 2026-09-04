"""XRS energy-loss axis: elastic-line calibration and momentum transfer.

The elastic line is the zero of energy loss; ``fit_elastic_line`` locates it
and ``to_energy_loss`` converts a mono-energy axis onto it. ``q_from_two_theta``
gives the momentum transfer that selects the dipole vs non-dipole regime.
"""
from __future__ import annotations

import numpy as np


# hc in eV·Å — converts photon energy to wavelength: lambda[Å] = _HC_EV_ANG / E[eV]
_HC_EV_ANG = 12398.419843320026

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
