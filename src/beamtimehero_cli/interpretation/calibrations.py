"""Literature calibration DATA for interpretation — cited, with validity domains.

Every entry is plain data with a ``source`` citation and a ``domain``:

- ``conventional`` — derived from transmission/total-yield XANES carrying
  the full core-hole lifetime broadening. Applying such a calibration to a
  HERFD spectrum requires re-broadening the HERFD spectrum with the
  tabulated core-hole width first (``descriptors.rebroaden``); results are
  stamped ``calibration_domain: herfd_rebroadened``.
- ``herfd`` — derived from HERFD measurements; valid on sharp spectra, but
  only for the same emission line.
- ``any`` — shape/relative statements that survive broadening.

Keeping calibrations as cited data (not buried logic) is what makes the
hybrid narration auditable and lets measured-standard calibrations swap in
later (Phase 2).
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Generic edge-shift-per-valence brackets (3d K-edges)
# ---------------------------------------------------------------------------

GENERIC_EDGE_SHIFT = {
    "ev_per_valence_range": (1.0, 3.0),
    "domain": "any",
    "source": (
        "Generic 3d K-edge bracket; element/ligand dependent. See e.g. "
        "Tromp & Moulin, Cr K-edge XANES (SLAC eConf C060709): Cr(VI) vs "
        "Cr(III) first-derivative edges differ by ~2.3 eV."
    ),
    "note": (
        "Low precision. Valid only for shifts measured against a "
        "same-element session reference on one E0 definition — never "
        "against tabulated database values."
    ),
}

PER_ELEMENT_EDGE_SHIFT = {
    # element -> eV per oxidation unit (approximate slope), with citation
    "Cr": {
        "ev_per_valence": 0.77,  # ~2.3 eV across Cr(III)->Cr(VI)
        "domain": "any",
        "source": (
            "Tromp & Moulin (SLAC eConf C060709, WEPO21): Cr K "
            "first-derivative edge 6003.3 eV Cr(III) vs 6005.6 eV Cr(VI)."
        ),
    },
}

# ---------------------------------------------------------------------------
# Fe K pre-edge (Wilke 2001) — the centroid/intensity (CII) method
# ---------------------------------------------------------------------------

WILKE_2001_FE_PRE_EDGE = {
    "domain": "conventional",
    "source": (
        "Wilke, Farges, Petit, Brown & Martin, Am. Mineral. 86, 714-730 "
        "(2001), DOI 10.2138/am-2001-5-612. Conventional Fe K-XANES "
        "(full 1s core-hole broadening, ~1.25 eV)."
    ),
    "centroid_fe2_ev": 7112.1,   # on the Fe-foil-first-inflection = 7112.0 scale
    "centroid_fe3_ev": 7113.5,
    "centroid_separation_ev": 1.4,
    "centroid_separation_unc_ev": 0.1,
    "energy_scale_note": (
        "Centroids are on Wilke's energy scale (Fe foil first inflection "
        "= 7112.0 eV). Comparing a measured centroid to these values "
        "requires a session calibration to the same convention."
    ),
    # Coarse total integrated pre-edge intensity brackets (area-normalized,
    # conventional broadening) for coordination readout. Approximate
    # envelopes from Wilke's CII diagram — treat as brackets, not lines.
    "intensity_brackets": {
        "octahedral_max": 0.08,
        "tetrahedral_min": 0.15,
        "note": (
            "Approximate envelopes from the Wilke 2001 CII diagram: "
            "6-coordinated (centrosymmetric) Fe gives weak pre-edges, "
            "4-coordinated (non-centrosymmetric) strong ones; between the "
            "brackets read as mixed/5-coordinated/distorted."
        ),
    },
}

# ---------------------------------------------------------------------------
# Ce L3 — Ce(IV) final-state doublet; NOT a single-white-line problem
# ---------------------------------------------------------------------------

CE_L3 = {
    "domain": "any",  # the doublet SHAPE survives broadening; positions need calibration
    "source": (
        "Standard Ce L3 XANES final-state analysis (e.g. Bianconi et al. "
        "PRB 35, 806 (1987); applied in HERFD in Inorg. Chem. 2021 "
        "lanthanide L3 studies)."
    ),
    "ce3_main_ev": 5726.0,
    "ce4_doublet_ev": (5729.0, 5737.0),  # 4f1L and 4f0 final states
    "note": (
        "Ce(III) (4f1): single main line. Ce(IV) (4f0): characteristic "
        "double peak (4f1L + 4f0). Valence fractions need multi-peak "
        "deconvolution or LCF; any single scalar is degenerate between "
        "intermediate valence and a mixture."
    ),
}

# ---------------------------------------------------------------------------
# U M4 HERFD — peak-position/satellite method (Kvashnina/Butorin school)
# ---------------------------------------------------------------------------

U_M4_HERFD = {
    "domain": "herfd",
    "emission_line": "Mbeta",
    "source": (
        "Bes et al., Inorg. Chem. 55, 4260 (2016), DOI "
        "10.1021/acs.inorgchem.6b00014 (U L3/M4 HERFD valence "
        "determination; Kvashnina/Butorin U M4 HERFD methodology)."
    ),
    "peak_positions_ev": {"U4": 3726.2, "U5": 3727.5, "U6_main": 3727.7},
    "u6_satellites_ev": (3729.6, 3733.4),
    "note": (
        "U(VI) uranyl shows the main line plus satellite structure "
        "(~+2/+6 eV) — a calibration-independent SHAPE signature. "
        "Absolute peak positions require session energy calibration."
    ),
}

# ---------------------------------------------------------------------------
# L3 white-line trends (5d metals / f-elements)
# ---------------------------------------------------------------------------

L3_WHITE_LINE_TREND = {
    "domain": "any",
    "source": (
        "L3 white-line area tracks unoccupied d-DOS / d-hole count "
        "(standard 5d practice, e.g. Pt/Ir XANES literature); higher "
        "oxidation -> higher white-line energy and intensity."
    ),
    "note": (
        "Relative/qualitative only in v1: intensity comparisons require "
        "identical normalization, emission line, and self-absorption "
        "regime. Quantitative d-hole counts need measured standards "
        "(Phase 2)."
    ),
}

CORE_HOLE_WIDTH_SOURCE = (
    "xraydb core_width (Krause & Oliver 1979 / Keski-Rahkonen & Krause "
    "1974 compilations)"
)
