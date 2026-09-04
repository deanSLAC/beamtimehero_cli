"""Moved — XAS descriptor figures now lives under ``science/``.

This module is a re-export shim kept so existing imports keep working.
New code should import from:

    beamtimehero_cli.science.plots.xas

See ``science/README.md`` for the layout and the rule it follows.
"""
from __future__ import annotations

from beamtimehero_cli.science.plots.xas import annotated_descriptor_figure  # noqa: F401
