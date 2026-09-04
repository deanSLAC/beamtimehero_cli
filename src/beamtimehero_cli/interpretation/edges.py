"""Moved — edge tables now lives under ``science/``.

This module is a re-export shim kept so existing imports keep working.
New code should import from:

    beamtimehero_cli.science.tables.edges

See ``science/README.md`` for the layout and the rule it follows.
"""
from __future__ import annotations

from beamtimehero_cli.science.tables.edges import (  # noqa: F401
    EDGE_ENERGY_SOURCE,
    _3D_Z,
    _4D_Z,
    _5D_K_Z,
    _MAIN_GROUP_K_Z,
    _LN_Z,
    _5D_Z,
    _AN_Z,
    _COMMON_ABSORBERS,
    classify_edge_family,
    get_edge_info,
    _candidate_edges,
    _TOL_EV,
    _K_EDGE_BONUS,
    _COMMON_BONUS,
    _AMBIGUITY_MARGIN,
    _suggestion_score,
    suggest_edge,
)
