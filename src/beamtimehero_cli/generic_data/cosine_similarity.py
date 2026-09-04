"""Moved — scan similarity now lives under ``science/``.

This module is a re-export shim kept so existing imports keep working.
New code should import from:

    beamtimehero_cli.science.fitting.similarity

See ``science/README.md`` for the layout and the rule it follows.
"""
from __future__ import annotations

from beamtimehero_cli.science.fitting.similarity import (  # noqa: F401
    compute_cosine_similarity,
    analyze_scan_quality,
)
