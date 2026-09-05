"""Mostly moved — the generic math now lives under ``science/``.

* ``generic_data.lcf``               -> ``science.xas.compare`` (shim)
* ``generic_data.cosine_similarity`` -> ``science.fitting.similarity`` (shim)

``generic_data.fitter`` holds the knife-edge, aperture and emission-peak fits.
"""

# Keep `import beamtimehero_cli.generic_data as g; g.cosine_similarity` working
# the way it did before the move.
from beamtimehero_cli.generic_data import (  # noqa: F401,E402
    cosine_similarity,
    lcf,
)
