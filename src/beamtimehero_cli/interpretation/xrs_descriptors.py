"""Moved — XRS descriptors now lives under ``science/``.

This module is a re-export shim kept so existing imports keep working.
New code should import from:

    beamtimehero_cli.science.xrs.descriptors

See ``science/README.md`` for the layout and the rule it follows.
"""
from __future__ import annotations

from beamtimehero_cli.science.xrs.descriptors import (  # noqa: F401
    _uniform,
    edge_onset,
    _window,
    peak_in_window,
    integrated_area,
    feature_snr,
    extract_xrs_descriptors,
)
