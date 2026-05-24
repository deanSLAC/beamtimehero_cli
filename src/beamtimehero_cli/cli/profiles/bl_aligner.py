"""bl-aligner profile — beamline-local alignment agent surface.

Placeholder; the bl-aligner team owns expansion. Today's surface is
just enough to prove the file-cache (``spec-file``) backend resolves
through the profile alias mechanism the same way ``k8s-agent`` resolves
through the S3DF backend.
"""
from __future__ import annotations

PROFILE = {
    "name": "bl-aligner",
    "description": "Beamline-local alignment agent (file-cache backend).",
    "aliases": {
        "list-scans":  ("spec-file", "list_scans"),
        "read-scan":   ("spec-file", "read_scan"),
        "plot-scan":   ("spec-file", "plot_scan"),
    },
}
