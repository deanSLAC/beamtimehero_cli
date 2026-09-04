"""Moved — the analysis math now lives under ``science/``.

This package is kept as re-export shims so existing imports keep working:

* ``analysis.xas``    -> ``science.reduce.*`` + ``science.xas.compare``
* ``analysis.exafs``  -> ``science.exafs.*``
* ``analysis.xrs``    -> ``science.xrs.*``
* ``analysis.render`` -> ``science.plots.scan``

See ``science/README.md`` for the layout and the rule it follows.
"""
