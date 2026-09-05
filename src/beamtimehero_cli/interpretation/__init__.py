"""Moved — scientific interpretation now lives under ``science/``.

Kept as a re-export shim. New code should import from
``beamtimehero_cli.science.xas`` (and ``science.tables`` for the edge tables).

See ``science/README.md``.
"""

from beamtimehero_cli.science.tables.edges import (  # noqa: F401
    classify_edge_family,
    get_edge_info,
    suggest_edge,
)
from beamtimehero_cli.science.xas.descriptors import (  # noqa: F401
    extract_descriptors,
    per_scan_descriptor_trends,
)
from beamtimehero_cli.science.xas.e0 import (  # noqa: F401
    find_e0,
    rebroaden,
)
from beamtimehero_cli.science.xas.interpret import (  # noqa: F401
    interpret_coordination_geometry,
    interpret_oxidation_state,
    summarize_chemistry,
)

# Pre-move, this package's __init__ imported *from* its submodules, which bound
# them as attributes — so `import beamtimehero_cli.interpretation as i;
# i.descriptors` worked. The new __init__ pulls from science.*, which would
# silently drop that. Re-bind the submodule names to keep the old surface.
from beamtimehero_cli.interpretation import (  # noqa: F401,E402
    calibration_store,
    calibrations,
    descriptors,
    edges,
    interpret,
    normalize,
    plotting,
    quality,
    xrs_descriptors,
    xrs_edges,
    xrs_interpret,
)
