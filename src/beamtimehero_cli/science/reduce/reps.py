"""Averaging and filtering across repeated scans (reps).

Technique-agnostic: operates on a DataFrame with one column per rep, rows
indexed by the scanned axis.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


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


# ---------------------------------------------------------------------------
# Aborted-rep filtering (multi-sweep files where a rep stopped mid-scan)
# ---------------------------------------------------------------------------

def filter_short_reps(
    combined: pd.DataFrame, min_span_frac: float = 0.8,
) -> tuple[pd.DataFrame, list[str]]:
    """Drop rep columns whose covered energy span is a fraction of the rest.

    Beamline data (notably SSRL BL 4-3 sweep files) includes aborted reps
    that stop after a handful of points; after tolerance-aligned concat
    they appear as columns that are NaN over most of the grid. Averaging
    them in biases the merge toward the pre-edge. A column is kept when
    the energy span of its non-NaN rows is at least ``min_span_frac`` of
    the largest span among the columns.

    Returns ``(filtered, dropped_names)``. Never drops everything — if all
    columns fall below the bar (degenerate input), the input is returned
    unchanged.
    """
    index = combined.index.values.astype(float)
    spans = {}
    for col in combined.columns:
        good = combined[col].notna().values
        spans[col] = float(index[good].max() - index[good].min()) if good.any() else 0.0
    best = max(spans.values(), default=0.0)
    if best <= 0:
        return combined, []
    keep = [c for c in combined.columns if spans[c] >= min_span_frac * best]
    if not keep:
        return combined, []
    dropped = [c for c in combined.columns if c not in keep]
    return combined[keep], dropped
