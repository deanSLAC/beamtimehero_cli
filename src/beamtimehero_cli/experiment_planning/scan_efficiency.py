"""Moved — scan repetition efficiency now lives under ``science/``.

This module is a re-export shim kept so existing imports keep working.
New code should import from:

    beamtimehero_cli.science.statistics.efficiency

See ``science/README.md`` for the layout and the rule it follows.
"""
from __future__ import annotations

from beamtimehero_cli.science.statistics.efficiency import (  # noqa: F401
    analyze_scan_efficiency,
)
