"""Moved — figure rendering now lives under ``science/``.

This module is a re-export shim kept so existing imports keep working.
New code should import from:

    beamtimehero_cli.science.plots.scan

See ``science/README.md`` for the layout and the rule it follows.
"""
from __future__ import annotations

from beamtimehero_cli.science.plots.scan import (  # noqa: F401
    fig_to_base64,
    render_scan,
)
