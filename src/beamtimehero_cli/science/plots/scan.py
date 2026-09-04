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
