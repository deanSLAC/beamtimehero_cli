"""XAS scan math — backend-agnostic.

Functions here take pandas DataFrames (one row per energy step, counter
columns) and return plain numeric arrays / dicts. No file or DB I/O.

Both files_backend and postgres_backend produce the same DataFrame shape
(index = scanned motor, columns = counters, df.attrs carries count_time
and motor_positions), so any analysis built on top is shared.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Active-counter selection
# ---------------------------------------------------------------------------

_VORT_CANDIDATES = ("vortDT", "vortDT2", "vortDT3", "vortDT4")


def pick_active_counter(df: pd.DataFrame) -> tuple[str, str]:
    """Pick the active fluorescence/absorption counter for a scan DataFrame.

    Returns ``(counter_name, reason)``. Decision logic:

    1. If ``ppboff`` is a counter, it is the active counter.
    2. Else among ``vortDT, vortDT2, vortDT3, vortDT4``, the one with the
       highest max wins.
    3. Otherwise default to ``I1``.
    """
    cols = set(df.columns)

    if "ppboff" in cols:
        return "ppboff", "ppboff counter present"

    available_vorts = [c for c in _VORT_CANDIDATES if c in cols]
    if available_vorts:
        best = max(available_vorts, key=lambda c: df[c].max())
        return best, f"highest max among {list(available_vorts)}"

    return "I1", "no ppboff or vortDT counters, defaulting to I1"


# ---------------------------------------------------------------------------
# Edge-step normalization
# ---------------------------------------------------------------------------

def edge_step_normalize(
    df: pd.DataFrame, counter: str, normalize_by: str | None = "I0",
) -> tuple[np.ndarray, np.ndarray]:
    """Apply edge-step normalization to a single counter on one scan.

    Pre-edge anchor = mean of first 10% of points.
    Post-edge anchor = mean of last 10% of points.
    Returns ``(energy, normalized_signal)`` numpy arrays.

    Raises:
        KeyError if ``counter`` or ``normalize_by`` is missing from the
        DataFrame.
    """
    if counter not in df.columns:
        raise KeyError(
            f"Counter '{counter}' not found. Available: {list(df.columns)}"
        )
    if normalize_by and normalize_by not in df.columns:
        raise KeyError(
            f"Normalization counter '{normalize_by}' not found. "
            f"Available: {list(df.columns)}"
        )

    energy = df.index.values.astype(float)
    signal = df[counter].values.astype(float)

    if normalize_by:
        i0 = df[normalize_by].values.astype(float)
        i0_safe = np.where(i0 == 0, 1.0, i0)
        signal = signal / i0_safe

    n = len(signal)
    n10 = max(1, n // 10)
    pre_mean = np.mean(signal[:n10])
    post_mean = np.mean(signal[-n10:])
    denom = post_mean - pre_mean
    if abs(denom) < 1e-15:
        normalized = signal - pre_mean
    else:
        normalized = (signal - pre_mean) / denom

    return energy, normalized


# ---------------------------------------------------------------------------
# Per-rep noise estimation (used by inverse-variance averaging)
# ---------------------------------------------------------------------------

def estimate_per_rep_noise(
    combined: pd.DataFrame, baseline_frac: float = 0.10,
) -> np.ndarray:
    """Estimate per-rep noise sigma from the std of the post-edge plateau.

    ``combined`` is a DataFrame with one column per rep (already edge-step
    normalized; rows indexed by energy). The last ``baseline_frac`` of
    rows define the post-edge plateau where every rep is ~1.0 by
    construction — any residual std is per-rep noise.

    Returns one sigma per column. Falls back to equal weights (1.0) when
    the baseline is too short or has zero std.
    """
    n_points = len(combined)
    n_baseline = max(5, int(n_points * baseline_frac))
    baseline = combined.iloc[-n_baseline:]
    sigmas = baseline.std(axis=0, ddof=1).values
    sigmas = np.where(np.isfinite(sigmas) & (sigmas > 0), sigmas, np.nan)
    if not np.any(np.isfinite(sigmas)):
        return np.ones(combined.shape[1])
    fallback = np.nanmedian(sigmas)
    sigmas = np.where(np.isfinite(sigmas), sigmas, fallback)
    return sigmas


# ---------------------------------------------------------------------------
# Averaging across reps
# ---------------------------------------------------------------------------

def average_reps(
    combined: pd.DataFrame, weighting: str = "equal",
) -> tuple[pd.Series, pd.Series, list[float] | None]:
    """Average edge-step normalized reps across the column dimension.

    ``combined`` has one column per rep. Returns ``(mean, std, weights)``
    where ``mean`` and ``std`` are Series indexed by energy. ``weights``
    is the per-rep weight list when ``weighting=="inverse_variance"``,
    else None.

    Raises ValueError for an unknown weighting strategy.
    """
    if weighting == "equal":
        return combined.mean(axis=1), combined.std(axis=1), None

    if weighting == "inverse_variance":
        sigmas = estimate_per_rep_noise(combined)
        weights = 1.0 / np.square(sigmas)
        weights = weights / weights.sum()
        avg = (combined.values * weights[np.newaxis, :]).sum(axis=1)
        diff = combined.values - avg[:, np.newaxis]
        var = (np.square(diff) * weights[np.newaxis, :]).sum(axis=1)
        std = np.sqrt(var)
        return (
            pd.Series(avg, index=combined.index),
            pd.Series(std, index=combined.index),
            [float(w) for w in weights],
        )

    raise ValueError(
        f"Unknown weighting '{weighting}'. Use 'equal' or 'inverse_variance'."
    )
