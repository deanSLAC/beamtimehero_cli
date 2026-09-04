"""Moved — EXAFS math now lives under ``science/``.

This module is a re-export shim kept so existing imports keep working.
New code should import from:

    beamtimehero_cli.science.exafs.kspace
    beamtimehero_cli.science.exafs.background
    beamtimehero_cli.science.exafs.fourier

See ``science/README.md`` for the layout and the rule it follows.
"""
from __future__ import annotations

from beamtimehero_cli.science.exafs.kspace import (  # noqa: F401
    ETOK,
    etok,
    ktoe,
    rebin_k,
)

from beamtimehero_cli.science.exafs.background import autobk_lite  # noqa: F401

from beamtimehero_cli.science.exafs.fourier import (  # noqa: F401
    ft_window,
    xftf,
    first_shell_peak,
)
