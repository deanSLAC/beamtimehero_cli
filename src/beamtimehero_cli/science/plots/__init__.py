"""Figures over arrays and descriptor dicts.

A figure function belongs here when it takes **arrays or a descriptor dict**.
A figure function that takes a **file name** belongs in
``beamtimehero_cli.spec_data`` instead — it needs to know where data lives, so
by the rule in this package's docstring it is not science.

* ``exafs`` — k- and R-space figures
* ``xrs``   — energy-loss figures
* ``xas``   — descriptor, alignment, difference and LCF figures
* ``scan``  — generic scan render, statistics trend, and ``fig_to_base64``

``spec_data/exafs_plotting.py`` and ``spec_data/xrs_plotting.py`` are now
re-export shims pointing here; ``spec_data/plotting.py`` keeps only the six
figures that load a scan by file name.
"""
