"""Scientific interpretation of HERFD XANES spectra.

Pure-science package: turns a normalized mu(E) spectrum into reproducible
numeric descriptors and grounded chemical interpretation (oxidation state,
coordination geometry). No SPEC/file/DB I/O except the session
energy-calibration record (``calibration_store``).

Rigor contract (see plan review):

- No absolute oxidation-state estimate is ever emitted without a session
  energy calibration against a measured reference (``calibration_store``).
- Literature calibrations carry an explicit validity domain
  (``conventional`` vs ``herfd``); conventional-domain calibrations (e.g.
  Wilke 2001) are applied only after re-broadening HERFD spectra with the
  tabulated core-hole width.
- Every intensity metric records the normalization that produced it
  (area normalization per Bugarin/Glatzel 2024 is the HERFD default).
- All numbers come from fits with propagated uncertainties; narration is
  assembled from those numbers, never invented.
"""

from beamtimehero_cli.interpretation.edges import (  # noqa: F401
    classify_edge_family,
    get_edge_info,
    suggest_edge,
)
from beamtimehero_cli.interpretation.descriptors import (  # noqa: F401
    extract_descriptors,
    find_e0,
    per_scan_descriptor_trends,
    rebroaden,
)
from beamtimehero_cli.interpretation.interpret import (  # noqa: F401
    interpret_coordination_geometry,
    interpret_oxidation_state,
    summarize_chemistry,
)
