"""Compatibility shim: ``REFERENCE_DOCS`` is now backed by the refdocs registry.

The :mod:`beamtimehero_cli.cli.__main__` dispatcher consumes
:data:`REFERENCE_DOCS` to build and serve the ``beamtimehero ref`` subtree.
Consumers register additional docs via :func:`beamtimehero_cli.refdocs.register_doc`.
"""
from __future__ import annotations

from beamtimehero_cli import refdocs


class _ReferenceDocsView:
    """dict-like view over the refdocs registry.

    Exposed under the historical name ``REFERENCE_DOCS`` so callers that
    iterate ``REFERENCE_DOCS.items()`` or do ``REFERENCE_DOCS[name]``
    continue to work. Items yield ``(name, {"file": Path, "description": str})``.
    """

    def __contains__(self, name: str) -> bool:
        return refdocs.has_doc(name)

    def __getitem__(self, name: str) -> dict:
        return {
            "file": refdocs.doc_path(name),
            "description": dict(refdocs.list_docs()).get(name, ""),
        }

    def items(self):
        for name, desc in refdocs.list_docs():
            yield name, {"file": refdocs.doc_path(name), "description": desc}

    def __iter__(self):
        for name, _ in refdocs.list_docs():
            yield name


REFERENCE_DOCS = _ReferenceDocsView()
