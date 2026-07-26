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

    .. warning::

       This is a *convenience default for the XAS/HERFD/XES case only*. The
       "highest max" heuristic silently picks a flat, high-offset background
       channel over the true signal when they coexist — the exact ``vortDT``
       (dark) vs ``vortDT2`` (signal) failure that corrupted an XRS dataset.
       Any tool that averages/compares/scores repeated scans MUST accept an
       explicit ``counter`` and only fall back here when none is given.
       See ``beamtimehero ref counter-selection``.
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
# Counter-selection guardrail (the vortDT-vs-vortDT2 trap)
# ---------------------------------------------------------------------------

# A channel whose fractional modulation (peak-to-peak / max) is below this is
# "flat" — the signature of a dark/background channel sitting at a large DC
# offset. See ``beamtimehero ref counter-selection``.
_FLAT_MODULATION_FRAC = 0.15


def _fractional_modulation(series) -> float:
    """(max - min) / max for one counter column. 0 for an all-zero channel."""
    v = np.asarray(series, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return 0.0
    hi = float(np.max(v))
    if hi <= 0:
        return 0.0
    return (hi - float(np.min(v))) / hi


def counter_selection_warning(df: pd.DataFrame, chosen: str) -> str | None:
    """Warn when an auto-picked counter looks like a flat dark/background channel.

    Returns a human-readable warning string, or None if the pick looks safe.
    The trap this catches: ``pick_active_counter`` chooses the ``vortDT*``
    channel with the highest max, but a flat dark channel at a large DC offset
    can out-max the real (small) signal channel. If the chosen counter is flat
    while a sibling ``vortDT*`` channel has much higher fractional modulation,
    the sibling is likely the real signal. See ``ref counter-selection``.
    """
    if chosen not in df.columns:
        return None
    chosen_mod = _fractional_modulation(df[chosen])
    if chosen_mod >= _FLAT_MODULATION_FRAC:
        return None
    siblings = [
        c for c in _VORT_CANDIDATES
        if c in df.columns and c != chosen
        and _fractional_modulation(df[c]) >= 2 * max(chosen_mod, 1e-6)
        and _fractional_modulation(df[c]) >= _FLAT_MODULATION_FRAC
    ]
    if not siblings:
        return None
    best_sib = max(siblings, key=lambda c: _fractional_modulation(df[c]))
    return (
        f"Auto-picked counter '{chosen}' is nearly flat "
        f"({chosen_mod * 100:.1f}% peak-to-peak modulation) — the signature of a "
        f"dark/background channel at a large DC offset. Channel '{best_sib}' "
        f"({_fractional_modulation(df[best_sib]) * 100:.1f}% modulation) is more "
        f"likely the real signal. Pass counter='{best_sib}' explicitly if this is "
        f"XRS or any non-edge technique. See `beamtimehero ref counter-selection`."
    )


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


# Normalization modes selectable by the multi-scan tools. ``edge_step`` is the
# XAS default; the others exist so off-edge techniques (XRS) are not forced
# through an edge-jump they don't have. See ``ref counter-selection``.
NORMALIZATION_MODES = ("edge_step", "divide_by_i0", "raw")


def normalize_series(
    df: pd.DataFrame, counter: str, normalize_by: str | None = "I0",
    mode: str = "edge_step",
) -> tuple[np.ndarray, np.ndarray]:
    """Normalize one scan's counter under a selectable mode.

    - ``edge_step`` — pre-edge→0, post-edge→1 (absorption-edge normalization).
      **Wrong for XRS**: there is no edge step to anchor to.
    - ``divide_by_i0`` — signal / I0 only. The right choice for XRS/non-edge
      data when a technique-specific normalization (area, Compton-subtracted)
      hasn't been applied yet — it analyzes the true signal without imposing an
      edge shape.
    - ``raw`` — the counter as recorded, no I0 division.

    Returns ``(energy, values)``. Raises KeyError for a missing counter/monitor,
    ValueError for an unknown mode.
    """
    if mode not in NORMALIZATION_MODES:
        raise ValueError(
            f"Unknown normalization mode '{mode}'. "
            f"Use one of {list(NORMALIZATION_MODES)}."
        )
    if counter not in df.columns:
        raise KeyError(
            f"Counter '{counter}' not found. Available: {list(df.columns)}"
        )
    if mode == "edge_step":
        return edge_step_normalize(df, counter, normalize_by=normalize_by)

    energy = df.index.values.astype(float)
    signal = df[counter].values.astype(float)
    if mode == "raw":
        return energy, signal
    # divide_by_i0
    if normalize_by:
        if normalize_by not in df.columns:
            raise KeyError(
                f"Normalization counter '{normalize_by}' not found. "
                f"Available: {list(df.columns)}"
            )
        i0 = df[normalize_by].values.astype(float)
        i0_safe = np.where(i0 == 0, 1.0, i0)
        signal = signal / i0_safe
    return energy, signal


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
