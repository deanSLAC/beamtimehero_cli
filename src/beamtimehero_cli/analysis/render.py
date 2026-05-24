"""Backend-agnostic figure rendering.

Phase 1 hosts ``fig_to_base64`` here as the single source of truth used
by both backends and any tool that emits an image. The per-plot figure
builders currently live in ``spec_data/plotting.py`` and will migrate
here in Phase 2 alongside the DataFrame-only refactor.
"""
from __future__ import annotations

import base64
import io


def fig_to_base64(fig) -> str:
    """Convert a matplotlib figure to a base64-encoded PNG string."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()
