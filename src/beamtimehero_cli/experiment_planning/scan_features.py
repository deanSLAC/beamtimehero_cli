"""Moved — per-rep feature statistics now live under ``science/``.

This module is a re-export shim kept so existing imports keep working.
New code should import from:

    beamtimehero_cli.science.statistics.features

See ``science/README.md`` for the layout and the rule it follows.
"""
from __future__ import annotations

from beamtimehero_cli.science.statistics.features import (  # noqa: F401
    VALID_STATISTICS,
    analyze_feature_evolution,
    analyze_scalar_convergence,
    extract_window_scalar,
    heterogeneity_f_statistic,
)
