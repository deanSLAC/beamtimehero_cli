"""Mostly moved — the pure statistics now live under ``science/statistics/``.

* ``experiment_planning.scan_features``   -> ``science.statistics.features`` (shim)
* ``experiment_planning.scan_efficiency`` -> ``science.statistics.efficiency`` (shim)

``decisions.py`` and ``scan_strategies.py`` have NOT moved: nothing imports
them (``decisions.py`` is the only route to ``generic_data.fitter``, and it has
no callers of its own). Both are left unrouted pending a decision on whether to
wire them up or delete them.
"""
