"""Per-agent CLI profiles.

Each profile is a Python module exposing a ``PROFILE`` dict that aliases
profile-leaf names (kebab-case) to ``(tree, ..., canonical_name)`` tuples
in the master tool catalog. Profiles are a *curated view* — they don't
add new tools, they just expose a subset under a per-agent top-level
branch (e.g. ``beamtimehero k8s-agent list-scans``).

Discovery is module-listdir at import time for profiles bundled with
this package. Out-of-tree consumers (e.g. the playground deployment)
register their profiles via :func:`register_profile`.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil

logger = logging.getLogger(__name__)

PROFILES: dict[str, dict] = {}


def register_profile(profile: dict) -> None:
    """Register an out-of-tree agent profile.

    The profile dict must contain ``name`` (str) and ``aliases``
    (mapping of kebab leaf name → canonical ``(tree, ..., name)``
    tuple). A ``description`` field is recommended for help text.

    Call this at startup, before any parser is built. Later calls
    overwrite earlier ones with the same name.
    """
    if not profile or not profile.get("name"):
        raise ValueError("Profile must include a non-empty 'name'.")
    PROFILES[profile["name"]] = profile


def _discover() -> None:
    for _finder, name, _ispkg in pkgutil.iter_modules(__path__):
        if name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"{__name__}.{name}")
        except Exception:  # noqa: BLE001
            logger.warning("Failed to import profile %r", name, exc_info=True)
            continue
        profile = getattr(mod, "PROFILE", None)
        if not profile or not profile.get("name"):
            continue
        PROFILES[profile["name"]] = profile


_discover()
