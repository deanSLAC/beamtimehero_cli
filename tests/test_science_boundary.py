"""The two structural properties that make ``science/`` a safe working area.

``science/README.md`` promises a contributor that they can work inside
``science/`` without reading the rest of the repo, and that a function's
purity is checkable from its signature. Both promises rest on invariants that
were true when they were written and had nothing keeping them true:

  1. ``science/`` imports nothing else from ``beamtimehero_cli``, so the
     package is a leaf and reading it does not drag in the toolbelt, and
  2. nothing under ``science/`` reads the environment, the filesystem, the
     network, or a database, so "numbers in, numbers out" holds.

This is the same gap ``test_science_policy.py`` closes for the scientific
defaults: the property was documented, correct, and unguarded. A boundary
nobody checks is a boundary that decays on the next commit that finds it
inconvenient.

These read the source with ``ast`` rather than importing, which catches
function-local imports — the usual way a layering rule gets bent — and
resolves relative imports, since ``from ...spec_data import x`` escapes
``science/`` just as surely as the absolute form.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

import beamtimehero_cli.science as science

SCIENCE_ROOT = pathlib.Path(science.__file__).parent
PACKAGE_ROOT = SCIENCE_ROOT.parent.parent          # .../src
ALLOWED_PREFIX = "beamtimehero_cli.science"

# Modules that would mean this code knows where data lives, who is asking, or
# what the machine is configured like. ``xraydb`` is deliberately absent: its
# tabulated edge energies ship inside the library as a read-only table, which
# science/README sanctions explicitly as a constant lookup rather than I/O.
FORBIDDEN_MODULES = {
    "argparse",
    "configparser",
    "dotenv",
    "os",
    "pathlib",
    "psycopg2",
    "requests",
    "shutil",
    "socket",
    "sqlite3",
    "sqlmodel",
    "subprocess",
    "sys",
    "tempfile",
    "urllib",
}

# Builtins that reach the filesystem regardless of which module they came from.
FORBIDDEN_CALLS = {"open", "getenv", "system", "popen"}


def _science_files():
    return sorted(SCIENCE_ROOT.rglob("*.py"))


def _rel(path: pathlib.Path) -> str:
    """``xas/normalize.py``, not ``normalize.py`` — there are two of those."""
    return path.relative_to(SCIENCE_ROOT).as_posix()


def _module_name(path: pathlib.Path) -> str:
    rel = path.relative_to(PACKAGE_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _package_of(path: pathlib.Path) -> str:
    mod = _module_name(path)
    if path.name == "__init__.py":
        return mod
    return mod.rpartition(".")[0]


def _imported_targets(path: pathlib.Path):
    """Every module this file imports, as an absolute dotted name.

    Relative imports are resolved against the file's own package so that
    ``from ...spec_data import x`` is reported as
    ``beamtimehero_cli.spec_data`` rather than slipping through.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    yield node.module, node.lineno
                continue
            base = _package_of(path).split(".")
            trimmed = base[: len(base) - (node.level - 1)] or base[:1]
            target = ".".join(trimmed + ([node.module] if node.module else []))
            yield target, node.lineno


@pytest.mark.parametrize("path", _science_files(), ids=_rel)
def test_science_imports_nothing_else_from_the_package(path):
    """``science/`` is a leaf: it may import itself and third-party code only.

    If this fails, the scientific core has grown a dependency on the toolbelt
    and can no longer be read — or tested — on its own. Move the thing you
    needed *into* ``science/``, or pass it in as an argument.
    """
    violations = [
        f"{_rel(path)}:{lineno} imports {target}"
        for target, lineno in _imported_targets(path)
        if target.startswith("beamtimehero_cli")
        and not target.startswith(ALLOWED_PREFIX)
    ]
    assert not violations, (
        "science/ must not import from the rest of beamtimehero_cli:\n  "
        + "\n  ".join(violations)
    )


@pytest.mark.parametrize("path", _science_files(), ids=_rel)
def test_science_does_not_touch_env_filesystem_or_network(path):
    """"Numbers in, numbers out" — checkable from the signature alone.

    A science function that reads a file or an env var cannot be called by a
    scientist with arrays in hand, and its behaviour stops being determined by
    its arguments. Data loading belongs in ``spec_data/``.
    """
    violations = []
    for target, lineno in _imported_targets(path):
        root = target.split(".")[0]
        if root in FORBIDDEN_MODULES:
            violations.append(f"{_rel(path)}:{lineno} imports {target}")

    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name in FORBIDDEN_CALLS:
            violations.append(f"{_rel(path)}:{node.lineno} calls {name}()")

    assert not violations, (
        "science/ must not read the environment, filesystem, or network:\n  "
        + "\n  ".join(violations)
        + "\nIf you need data loaded, take it as an argument and let "
          "spec_data/ do the loading."
    )
