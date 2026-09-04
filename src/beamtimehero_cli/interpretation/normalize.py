"""Moved — XAS normalization now lives under ``science/``.

This module is a re-export shim kept so existing imports keep working.
New code should import from:

    beamtimehero_cli.science.xas.normalize

See ``science/README.md`` for the layout and the rule it follows.
"""
from __future__ import annotations

from beamtimehero_cli.science.xas.normalize import (  # noqa: F401
    _emission_energy_ev,
    AREA_NORM_CITATION,
    MBACK_CITATION,
    DEFAULT_AREA_WINDOW,
    area_normalize,
    edge_step_provenance,
    mback_normalize,
    pre_post_normalize,
)
