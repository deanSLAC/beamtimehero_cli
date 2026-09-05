"""Moved — EXAFS figures now live under ``science/plots/``.

These take arrays, not file names, so by the rule in ``science/README.md``
they are science. This module is a re-export shim kept so existing imports
keep working. New code should import from:

    beamtimehero_cli.science.plots.exafs

``fig_to_base64`` is re-exported here too, because callers have imported it
from this module since before the science/ split.
"""
from __future__ import annotations

from beamtimehero_cli.science.plots.exafs import (  # noqa: F401
    plot_chi_extraction,
    plot_chir,
    plot_chi_overlay,
)
from beamtimehero_cli.science.plots.scan import fig_to_base64  # noqa: F401
