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
