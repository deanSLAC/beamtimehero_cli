"""Moved — XRS edge tables now lives under ``science/``.

This module is a re-export shim kept so existing imports keep working.
New code should import from:

    beamtimehero_cli.science.tables.xrs_edges

See ``science/README.md`` for the layout and the rule it follows.
"""
from __future__ import annotations

from beamtimehero_cli.science.tables.xrs_edges import (  # noqa: F401
    _XRS_EDGES,
    _3D_L,
    classify_xrs_family,
    get_xrs_edge_info,
    _AMBIGUITY_MARGIN_EV,
    suggest_xrs_edge,
)
