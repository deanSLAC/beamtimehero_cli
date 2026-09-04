"""Data-quality gating for interpretation: glitches, saturation, self-absorption.

Interpretation runs after the existing SNR/convergence tooling, but fits
(E0 derivative, pre-edge peaks) are far more sensitive to single-point
artifacts than averages are — so glitch masking happens here, immediately
before any fit, and every applied mask is reported in the output flags.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import medfilt


def detect_glitches(
    energy: np.ndarray,
    mu: np.ndarray,
    z_threshold: float = 8.0,
    window: int = 7,
) -> np.ndarray:
    """Boolean mask of monochromator-glitch-like spikes.

    A point is a glitch when its residual against a running median exceeds
    ``z_threshold`` robust sigmas (MAD-scaled). The running median tracks
    the edge/white-line shape, so genuine XANES features survive; only
    single-/few-point spikes are flagged. The high default threshold is
    deliberate — for interpretation a missed glitch is recoverable (fits
    are overdetermined) but masking a real pre-edge peak is not.
    """
    n = len(mu)
    if n < window + 2:
        return np.zeros(n, dtype=bool)
    if window % 2 == 0:
        window += 1
    residual = mu - medfilt(mu, kernel_size=window)
    mad = np.median(np.abs(residual - np.median(residual)))
    # Floor the scale estimate: on very clean (or synthetic) data the MAD
    # collapses to ~0 and a spike would divide by nothing. 0.1% of the
    # spectrum's range is far below any real noise level.
    scale = max(1.4826 * mad, 1e-3 * (np.max(mu) - np.min(mu)), 1e-12)
    z = np.abs(residual - np.median(residual)) / scale
    return z > z_threshold


def interpolate_over_mask(
    energy: np.ndarray, mu: np.ndarray, mask: np.ndarray,
) -> np.ndarray:
    """Replace masked points by linear interpolation from unmasked neighbors."""
    if not mask.any() or mask.all():
        return mu
    out = mu.copy()
    good = ~mask
    out[mask] = np.interp(energy[mask], energy[good], mu[good])
    return out


def detect_saturation(mu: np.ndarray, rel_tol: float = 1e-4) -> dict:
    """Flat-top check: many consecutive points pinned at the maximum.

    A flat-topped white line is the signature of detector saturation /
    deadtime clipping — intensity metrics from such data are invalid.
    """
    peak = np.max(mu)
    if peak <= 0:
        return {"saturated": False, "n_pinned": 0}
    pinned = np.abs(mu - peak) < rel_tol * abs(peak)
    # longest run of consecutive pinned points
    longest = run = 0
    for p in pinned:
        run = run + 1 if p else 0
        longest = max(longest, run)
    return {"saturated": longest >= 4, "n_pinned": int(longest)}


def self_absorption_assessment(assume_dilute: bool | None = None) -> dict:
    """Honest self-absorption risk statement for fluorescence-detected HERFD.

    Over-absorption damps the white line most strongly and biases every
    intensity-based valence/coordination metric. Without sample
    composition and geometry we cannot correct or even quantify it, so the
    assessment is declared, not guessed: ``assume_dilute=True`` is an
    explicit operator/agent assertion recorded in provenance.
    """
    if assume_dilute is True:
        return {
            "risk": "low_by_assertion",
            "note": (
                "Caller asserted a dilute/thin sample; intensity metrics "
                "treated as undistorted. This assertion is recorded, not "
                "verified."
            ),
        }
    return {
        "risk": "unknown",
        "note": (
            "Fluorescence-detected HERFD intensities may be damped by "
            "self-absorption (strongest at the white line) depending on "
            "concentration/thickness/geometry. Intensity-based verdicts "
            "carry degraded confidence until the sample is asserted dilute "
            "(assume_dilute) or measured standards exist (Phase 2)."
        ),
    }
