"""Statistics over a set of repeated scans — is it converged, is it enough?

Technique-agnostic, and a distinct job from ``reduce/``: that package turns
detector counts into one spectrum, this one judges a *stack* of reps.

    features.py    per-rep scalar over an agent-chosen energy window, its
                   running mean / SEM / convergence verdict, and a
                   heterogeneity F-statistic across sample spots
    efficiency.py  repetition efficiency — CV, Poisson-limit comparison,
                   optimal scan count, synthesized verdict

Named for what it computes rather than what consumes it. These functions back
the ``analyze-convergence`` / ``analyze-efficiency`` / ``analyze-per-spot`` /
``detect-per-scan-drift`` tools, and the experiment-planning logic in
consuming applications reads their output — but nothing here decides what to
scan next. That decision is the caller's.
"""
