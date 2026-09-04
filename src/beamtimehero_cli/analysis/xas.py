"""Moved — XAS/reduction math now lives under ``science/``.

This module is a re-export shim kept so existing imports keep working.
New code should import from:

    beamtimehero_cli.science.reduce.counters
    beamtimehero_cli.science.reduce.normalize
    beamtimehero_cli.science.reduce.reps
    beamtimehero_cli.science.reduce.deadtime
    beamtimehero_cli.science.xas.compare

See ``science/README.md`` for the layout and the rule it follows.
"""
from __future__ import annotations

from beamtimehero_cli.science.reduce.counters import (  # noqa: F401
    _VORT_CANDIDATES,
    pick_active_counter,
    _FLAT_MODULATION_FRAC,
    _fractional_modulation,
    counter_selection_warning,
)

from beamtimehero_cli.science.reduce.normalize import (  # noqa: F401
    edge_step_normalize,
    NORMALIZATION_MODES,
    normalize_series,
)

from beamtimehero_cli.science.reduce.reps import (  # noqa: F401
    estimate_per_rep_noise,
    average_reps,
    filter_short_reps,
)

from beamtimehero_cli.science.reduce.deadtime import deadtime_correct  # noqa: F401

from beamtimehero_cli.science.xas.compare import (  # noqa: F401
    MAX_ALIGN_SHIFT_EV,
    align_spectra,
    difference_spectrum,
    compare_to_references,
)
