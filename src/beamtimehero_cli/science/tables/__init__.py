"""Tabulated physics — the reference data, with the lookups over it.

Mostly data. The exception is edge *selection*: ``edges.py`` and
``xrs_edges.py`` also hold the scoring that picks the most plausible edge for
a scan energy window, because those tunables (tolerances, per-family bonuses,
an ambiguity margin) are meaningless away from the table they score against.

Edge energies and families, per-element edge-shift slopes, core-hole widths,
valence spans, preferred emission lines, XRS edge assignments. Each table
carries the citation for its source.

These are the values most often corrected or extended, and reading them
requires no knowledge of the rest of the codebase.
"""
