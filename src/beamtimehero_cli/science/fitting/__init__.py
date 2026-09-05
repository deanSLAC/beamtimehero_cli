"""Generic fitting and similarity helpers — not spectroscopy.

Currently holds only ``similarity.py`` (scan-to-scan cosine similarity, used
for convergence and quality checks).

The knife-edge, aperture and emission-peak fits for beam diagnostics and
alignment are in ``beamtimehero_cli.generic_data.fitter`` and have **not**
moved here — nothing in the tool catalog reaches them. This package is where
they would go.
"""
