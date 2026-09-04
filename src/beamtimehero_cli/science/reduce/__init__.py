"""Detector counts -> one clean spectrum. Technique-agnostic.

Counter selection, per-scan monitor normalization, averaging across repeated
scans, dead-time correction, and glitch/saturation/self-absorption flags.

Nothing here assumes an absorption edge, so it applies equally to XAS, EXAFS
and XRS. Technique-specific processing starts in ``xas/``, ``exafs/``, ``xrs/``.
"""
