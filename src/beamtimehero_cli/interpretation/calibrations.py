"""Moved — edge-shift tables now lives under ``science/``.

This module is a re-export shim kept so existing imports keep working.
New code should import from:

    beamtimehero_cli.science.tables.edge_shifts

See ``science/README.md`` for the layout and the rule it follows.
"""
from __future__ import annotations

from beamtimehero_cli.science.tables.edge_shifts import (  # noqa: F401
    GENERIC_EDGE_SHIFT,
    PER_ELEMENT_EDGE_SHIFT,
    MAX_VALENCE_SPAN,
    DEFAULT_VALENCE_SPAN,
    WILKE_2001_FE_PRE_EDGE,
    CE_L3,
    U_M4_HERFD,
    L3_WHITE_LINE_TREND,
    CORE_HOLE_WIDTH_SOURCE,
)
