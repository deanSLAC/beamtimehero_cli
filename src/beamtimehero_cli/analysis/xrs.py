"""Moved — XRS math now lives under ``science/``.

This module is a re-export shim kept so existing imports keep working.
New code should import from:

    beamtimehero_cli.science.xrs.calibrate
    beamtimehero_cli.science.xrs.reduce

See ``science/README.md`` for the layout and the rule it follows.
"""
from __future__ import annotations

from beamtimehero_cli.science.xrs.calibrate import (  # noqa: F401
    _HC_EV_ANG,
    q_from_two_theta,
    fit_elastic_line,
    to_energy_loss,
    common_loss_grid,
)

from beamtimehero_cli.science.xrs.reduce import (  # noqa: F401
    _trapz,
    align_and_average,
    _der_snr,
    reject_outlier_channels,
    sum_crystals,
    BACKGROUND_MODELS,
    subtract_compton_background,
    area_normalize,
)
