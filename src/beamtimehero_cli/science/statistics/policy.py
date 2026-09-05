"""Statistics policy — the convergence and repetition-efficiency thresholds.

Sibling to ``reduce/policy.py`` and the three technique policy modules. These
decide when a scan series is called converged and when more repetitions stop
paying for themselves — which is to say, when a user is told to stop
collecting. That is a scientific judgement with beamtime attached, so it is
pinned rather than left inline.
"""
from __future__ import annotations

# Standard error of the mean, as a fraction of the feature value, below which a
# scalar is called converged. 1% is the point where the SEM is comfortably
# under the systematic error of the descriptors themselves, so further
# repetitions buy precision that nothing downstream can use.
DEFAULT_SEM_THRESHOLD_FRAC = 0.01

# Drift in the running mean, as a fraction of the feature value, above which a
# series is called drifting rather than converged. Same scale as the SEM
# threshold on purpose: a trend smaller than the noise floor is not a trend.
DEFAULT_DRIFT_THRESHOLD_FRAC = 0.01

# Marginal improvement in the convergence metric, per additional repetition,
# below which further repetitions are called wasteful.
DEFAULT_EFFICIENCY_THRESHOLD = 0.05

# Floor on the recommended repetition count. Two reps is the minimum that
# permits any scatter estimate at all, so it is never sensible to recommend
# fewer regardless of what the efficiency curve says.
DEFAULT_MIN_RECOMMENDED_SCANS = 2

# ---------------------------------------------------------------------------
# CITATIONS — method -> reference. ``None`` means the method is implemented
# but not yet attributed; those surface as gaps on the generated science
# index, and filling one in is a welcome contribution. See science/README.md.
# ---------------------------------------------------------------------------

CITATIONS = {
    "SEM-fraction convergence criterion": None,
    "Running-mean drift criterion": None,
    "Marginal-efficiency stopping rule": None,
    "Poisson-limit comparison for repetition efficiency": None,
}
