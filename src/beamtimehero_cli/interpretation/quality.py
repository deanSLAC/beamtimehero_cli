"""Moved — spectrum artifact flags now lives under ``science/``.

This module is a re-export shim kept so existing imports keep working.
New code should import from:

    beamtimehero_cli.science.reduce.artifacts

See ``science/README.md`` for the layout and the rule it follows.
"""
from __future__ import annotations

from beamtimehero_cli.science.reduce.artifacts import (  # noqa: F401
    detect_glitches,
    interpolate_over_mask,
    detect_saturation,
    self_absorption_assessment,
)
