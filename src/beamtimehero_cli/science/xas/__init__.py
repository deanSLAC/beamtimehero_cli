"""XANES / HERFD: normalization, descriptors, and chemical interpretation.

Pipeline order: ``normalize`` -> ``e0`` -> ``fits`` -> ``descriptors`` ->
``interpret``, with ``compare`` for cross-spectrum work (registration,
differences, linear-combination fitting).

``policy`` holds the defaults and heuristics — fit windows, white-line
component counts, edge auto-detection, data-adequacy limits. Change a default
there, not at the call site.

Rigor contract:

- No absolute oxidation-state estimate without a session energy calibration
  against a measured reference (see ``beamtimehero_cli.calibration_store``).
- Literature calibrations carry an explicit validity domain (``conventional``
  vs ``herfd``); conventional-domain calibrations (e.g. Wilke 2001) are applied
  only after re-broadening HERFD spectra with the tabulated core-hole width.
- Every intensity metric records the normalization that produced it (area
  normalization per Bugarin & Glatzel 2024 is the HERFD default).
- All numbers come from fits with propagated uncertainties; narration is
  assembled from those numbers, never invented.
"""
