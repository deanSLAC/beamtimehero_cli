"""Backend-agnostic figure rendering.

Functions take pandas DataFrames + identifying metadata and return
``(fig, summary_text)``. They never touch disk, the DB, or the SPEC
session — backends are responsible for loading data and then handing
it to a renderer.
"""
from __future__ import annotations

import base64
import io
from typing import Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def fig_to_base64(fig) -> str:
    """Convert a matplotlib figure to a base64-encoded PNG string."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def render_scan(
    df: pd.DataFrame,
    file_name: str,
    scan_number: int,
    counter: Optional[str] = None,
    normalize_by: Optional[str] = None,
    scan_command: Optional[str] = None,
):
    """Render one scan's DataFrame to a matplotlib Figure.

    If ``counter`` is omitted, every column is plotted (useful for
    a quick raw view). ``normalize_by``, if set, divides ``counter``
    pointwise. ``scan_command`` is shown in the title when given.

    Returns ``(fig, summary)``. On error the figure is closed and
    returns ``(None, error_message)``.
    """
    fig, ax = plt.subplots(figsize=(8, 5))
    x_label = df.index.name or "index"

    if counter:
        if counter not in df.columns:
            plt.close(fig)
            return None, (
                f"Counter '{counter}' not found. Available: {list(df.columns)}"
            )
        y = df[counter]
        if normalize_by:
            if normalize_by not in df.columns:
                plt.close(fig)
                return None, f"Normalization counter '{normalize_by}' not found."
            y = y / df[normalize_by]
            y_label = f"{counter}/{normalize_by}"
        else:
            y_label = counter
        ax.plot(df.index, y)
        ax.set_ylabel(y_label)
    else:
        for col in df.columns:
            ax.plot(df.index, df[col], label=col)
        ax.legend(fontsize=8)
        y_label = "counts"

    ax.set_xlabel(x_label)
    title = f"{file_name} scan #{scan_number}"
    if scan_command:
        title += f"\n{scan_command}"
    ax.set_title(title, fontsize=10)
    fig.tight_layout()

    parts = [
        f"Plot of {file_name} scan #{scan_number}",
        f"X axis: {x_label} ({len(df)} points)",
    ]
    if counter:
        parts.append(f"Y axis: {y_label}")
        parts.append(f"Range: {float(y.min()):.4g} to {float(y.max()):.4g}")
    else:
        parts.append(f"Counters plotted: {list(df.columns)}")
    if scan_command:
        parts.append(f"Command: {scan_command}")

    summary = ". ".join(parts) + "."
    return fig, summary


def plot_statistics_trend(stats, sample_name=""):
    """Render a two-subplot statistics trend from pre-computed convergence stats.

    Parameters
    ----------
    stats : dict
        convergence_stats dict stored per-sample in the plan JSON. Expected
        keys: feature_window_eV, cumulative_cv_pct, running_sem_frac,
        efficiency_verdict, feature_verdict, statistic.
    sample_name : str
        Sample name for the plot title.

    Returns
    -------
    (fig, summary_text) or (None, error_text)
    """
    cv_pct = stats.get("cumulative_cv_pct")
    sem_frac = stats.get("running_sem_frac")
    if not cv_pct or not sem_frac:
        return None, "convergence_stats missing cumulative_cv_pct or running_sem_frac"

    n = len(cv_pct)
    reps = np.arange(1, n + 1)
    cv_arr = np.array(cv_pct, dtype=float)
    sem_arr = np.array([(v if v is not None else np.nan) for v in sem_frac], dtype=float) * 100

    window = stats.get("feature_window_eV") or [None, None]
    sem_threshold = stats.get("sem_threshold_frac", 0.01) * 100
    eff_verdict = stats.get("efficiency_verdict", "?")
    feat_verdict = stats.get("feature_verdict", "?")

    fig, (ax_cv, ax_sem) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    # --- Top: Cumulative CV ---
    ax_cv.plot(reps, cv_arr, "o-", color="C0", markersize=4, label="Cumulative CV")
    poisson_cv = cv_arr[0] / np.sqrt(reps)
    ax_cv.plot(reps, poisson_cv, "--", color="gray", alpha=0.7, label="1/√n Poisson")
    ax_cv.set_ylabel("Cumulative CV (%)")
    ax_cv.legend(fontsize=7, loc="upper right")
    ax_cv.grid(alpha=0.3)

    # --- Bottom: Feature SEM ---
    # Rep 1 has SEM=0 by definition (single sample); skip it so the
    # axis isn't pinned to zero.
    sem_reps = reps[1:]
    sem_vals = sem_arr[1:]
    ax_sem.plot(sem_reps, sem_vals, "o-", color="C0", markersize=4,
                label="Feature SEM (% of mean)")
    finite_mask = np.isfinite(sem_vals) & (sem_vals > 0)
    if finite_mask.sum() >= 2:
        first = int(np.where(finite_mask)[0][0])
        anchor = sem_vals[first]
        anchor_rep = sem_reps[first]
        poisson_sem = anchor * np.sqrt(anchor_rep) / np.sqrt(sem_reps)
        ax_sem.plot(sem_reps, poisson_sem, "--", color="gray", alpha=0.7,
                    label="1/√n Poisson")
    ax_sem.axhline(sem_threshold, color="C1", linestyle="-", alpha=0.6,
                   label=f"{sem_threshold:.0f}% publication threshold")
    ax_sem.set_ylabel("SEM (% of mean)")
    ax_sem.set_xlabel("Rep #")
    ax_sem.legend(fontsize=7, loc="upper right")
    ax_sem.grid(alpha=0.3)

    e_min, e_max = window
    window_str = f"[{e_min}, {e_max}] eV" if e_min is not None else ""
    title = (
        f"{sample_name} — statistics trend {window_str} "
        f"(CV: {eff_verdict}, SEM: {feat_verdict})"
    )
    fig.suptitle(title, fontsize=9)
    fig.tight_layout()

    summary = (
        f"Statistics trend for {sample_name}: "
        f"CV verdict={eff_verdict}, feature verdict={feat_verdict}, "
        f"final CV={cv_arr[-1]:.2f}%, final SEM={sem_arr[-1]:.2f}%."
    )
    return fig, summary
