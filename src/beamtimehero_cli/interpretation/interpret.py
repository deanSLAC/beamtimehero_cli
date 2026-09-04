"""Moved — XAS interpretation now lives under ``science/``.

This module is a re-export shim kept so existing imports keep working.
New code should import from:

    beamtimehero_cli.science.xas.interpret

See ``science/README.md`` for the layout and the rule it follows.
"""
from __future__ import annotations

from beamtimehero_cli.science.xas.interpret import (  # noqa: F401
    cal,
    _verdict,
    _degrade,
    interpret_oxidation_state,
    _oxidation_3d_k,
    _oxidation_4d_k,
    _oxidation_5d_k,
    _oxidation_main_group_k,
    _oxidation_fe_pre_edge,
    _K_EDGE_SHELL,
    _MAX_PLAUSIBLE_SHIFT_EV,
    _MAX_ESTIMATE_UNC,
    _shift_quality,
    _oxidation_k_edge_shift,
    _oxidation_ln_l3,
    _oxidation_an_m,
    _oxidation_5d_l3,
    _oxidation_unsupported,
    interpret_coordination_geometry,
    summarize_chemistry,
)
