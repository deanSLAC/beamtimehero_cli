"""Reference doc registry — bundled markdown shipped with the package.

Public API:
    list_docs() -> list[(name, description)]
    get_doc(name) -> str   # raises KeyError / FileNotFoundError
    register_doc(name, path, description)

Defaults under :mod:`beamtimehero_cli.refdocs.defaults` self-register on
import. Consumers can add their own via ``register_doc``.
"""
from __future__ import annotations

from pathlib import Path

_DEFAULTS_DIR = Path(__file__).resolve().parent / "defaults"

_DOCS: dict[str, dict] = {
    "getting-started": {
        "file": _DEFAULTS_DIR / "getting-started.md",
        "description": "Quick overview of the beamtimehero CLI surface.",
    },
    "action-log": {
        "file": _DEFAULTS_DIR / "action-log.md",
        "description": "Action-log schema and how each CLI invocation is recorded.",
    },
}


def register_doc(name: str, path: str | Path, description: str) -> None:
    """Register an additional reference doc.

    Consumers call this at startup to surface project-specific docs through
    the same ``beamtimehero ref`` command.
    """
    _DOCS[name] = {"file": Path(path), "description": description}


def list_docs() -> list[tuple[str, str]]:
    return [(name, info["description"]) for name, info in _DOCS.items()]


def get_doc(name: str) -> str:
    if name not in _DOCS:
        raise KeyError(name)
    return Path(_DOCS[name]["file"]).read_text()


def has_doc(name: str) -> bool:
    return name in _DOCS


def doc_path(name: str) -> Path:
    return Path(_DOCS[name]["file"])
