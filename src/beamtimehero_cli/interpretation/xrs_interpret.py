"""Moved — XRS interpretation now lives under ``science/``.

This module is a re-export shim kept so existing imports keep working.
New code should import from:

    beamtimehero_cli.science.xrs.interpret

See ``science/README.md`` for the layout and the rule it follows.
"""
from __future__ import annotations

from beamtimehero_cli.science.xrs.interpret import (  # noqa: F401
    _verdict,
    interpret_xrs_oxidation_state,
    interpret_q_dependence,
    compare_xrs_to_references,
    assess_xrs_quality,
    summarize_xrs_chemistry,
)
