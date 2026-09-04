"""Moved — XANES descriptors now lives under ``science/``.

This module is a re-export shim kept so existing imports keep working.
New code should import from:

    beamtimehero_cli.science.xas.e0
    beamtimehero_cli.science.xas.fits
    beamtimehero_cli.science.xas.descriptors

See ``science/README.md`` for the layout and the rule it follows.
"""
from __future__ import annotations

from beamtimehero_cli.science.xas.e0 import (  # noqa: F401
    E0_DEFINITION,
    _uniform,
    _odd_window_points,
    find_e0,
    rebroaden,
)

from beamtimehero_cli.science.xas.fits import (  # noqa: F401
    PRE_EDGE_WINDOW_REL,
    WHITE_LINE_WINDOW_REL,
    _BIC_MARGIN,
    _initial_peak_centers,
    fit_peak_region,
    fit_white_line,
    fit_pre_edge,
)

from beamtimehero_cli.science.xas.descriptors import (  # noqa: F401
    quality,
    _trend_stats,
    per_scan_descriptor_trends,
    extract_descriptors,
)
