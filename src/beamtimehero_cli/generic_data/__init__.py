"""Mostly moved — the generic math now lives under ``science/``.

* ``generic_data.lcf``               -> ``science.xas.compare`` (shim)
* ``generic_data.cosine_similarity`` -> ``science.fitting.similarity`` (shim)

``generic_data.fitter`` has NOT moved: it is reachable only through
``experiment_planning.decisions``, which nothing imports. Both are left
unrouted pending a decision on whether to wire them up under
``science/fitting/`` or delete them.
"""
