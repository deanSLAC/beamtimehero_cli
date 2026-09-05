"""XRS analysis policy — the energy-loss defaults, in one place.

Same purpose as :mod:`beamtimehero_cli.science.xas.policy` and
:mod:`beamtimehero_cli.science.exafs.policy`: the scientific *choices*, named
once, so changing one is a single edit and each can carry its citation.

Before this existed the Compton background model default sat as the literal
``"linear"`` in nine places (the reduction signature, four tool schemas and
five handler call sites), and the q-regime boundary was an unnamed ``3.0``
inside a handler.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Compton background
# ---------------------------------------------------------------------------

# Models available for the Compton background under an XRS edge. The Compton
# profile is broad and smooth relative to the edge, so over the narrow flanks
# either side of the feature a low-order form is enough.
BACKGROUND_MODELS = ("constant", "linear", "pearson7")

# 'linear' is the default: across a typical edge window the Compton profile is
# locally linear, and it is the lowest-order model that still absorbs the
# profile's slope (a constant leaves a tilt in the subtracted edge).
DEFAULT_BACKGROUND_MODEL = "linear"


# ---------------------------------------------------------------------------
# Momentum-transfer regime
# ---------------------------------------------------------------------------

# Boundary (A^-1) between the dipole-dominated regime, where an XRS spectrum is
# comparable to a XANES spectrum, and the regime where non-dipole (monopole /
# quadrupole) transitions gain enough weight that the comparison stops holding.
# Approximate and technique-wide, not element-specific — it selects which
# interpretation is defensible, so it is reported alongside q rather than
# silently applied.
DIPOLE_REGIME_Q_MAX_INV_ANG = 3.0

LOW_Q_LABEL = "low-q (dipole/XANES-like)"
HIGH_Q_LABEL = "high-q (multipole)"


def q_regime(q_inv_ang: float) -> str:
    """Label the scattering regime for a momentum transfer, in A^-1."""
    return (LOW_Q_LABEL if float(q_inv_ang) < DIPOLE_REGIME_Q_MAX_INV_ANG
            else HIGH_Q_LABEL)


# ---------------------------------------------------------------------------
# CITATIONS — method -> reference. ``None`` means the method is implemented
# but not yet attributed; those surface as gaps on the generated science
# index, and filling one in is a welcome contribution. See science/README.md.
# ---------------------------------------------------------------------------

CITATIONS = {
    "Compton background models (constant / linear / Pearson VII)": None,
    "Dipole vs non-dipole regime boundary in q": None,
}
