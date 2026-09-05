"""Reduction policy — the artifact and repetition-averaging defaults.

Sibling to ``xas/policy.py``, ``exafs/policy.py`` and ``xrs/policy.py``. These
defaults used to sit inline as keyword arguments, which meant nothing pinned
them: changing one left the whole suite green, even though a glitch threshold
decides which points reach a fit. They are as scientifically material as the
technique defaults, so they live here and are pinned alongside them.

Technique-agnostic on purpose — nothing here assumes an absorption edge.
"""
from __future__ import annotations

# Robust-sigma (MAD-scaled) residual above which a point counts as a
# monochromator glitch. Deliberately high: for interpretation a missed glitch
# is recoverable, because the fits are overdetermined, but masking a real
# pre-edge peak is not. Asymmetric costs, so the threshold is asymmetric too.
DEFAULT_GLITCH_Z_THRESHOLD = 8.0

# Running-median kernel width (points) the glitch residual is taken against.
# Wide enough to ride over the edge and white-line shape, narrow enough that a
# few-point spike still stands out. Forced odd by medfilt.
DEFAULT_GLITCH_WINDOW = 7

# Fractional tolerance for calling a point "pinned at the maximum" when
# detecting a flat-topped white line. 1e-4 of the peak is well inside any real
# counting noise, so a run of pinned points means saturation or deadtime
# clipping rather than a genuinely flat feature.
DEFAULT_SATURATION_REL_TOL = 1e-4

# Fraction of the spectrum, taken from the high-energy end, used as the
# post-edge plateau when estimating per-rep noise. The plateau is where scatter
# is noise rather than structure.
DEFAULT_NOISE_BASELINE_FRAC = 0.1

# Minimum energy span a repetition must cover, as a fraction of the longest
# rep in the set, before it is averaged in. Aborted scans are common and a
# short rep otherwise drags the average's endpoints around.
DEFAULT_MIN_REP_SPAN_FRAC = 0.8

# ---------------------------------------------------------------------------
# CITATIONS — method -> reference. ``None`` means the method is implemented
# but not yet attributed; those surface as gaps on the generated science
# index, and filling one in is a welcome contribution. See science/README.md.
# ---------------------------------------------------------------------------

CITATIONS = {
    "MAD-scaled robust z for glitch detection": None,
    "Glitch threshold chosen against fit sensitivity, not detection rate": None,
    "Flat-top saturation criterion": None,
    "Post-edge plateau as the per-rep noise estimator": None,
}
