"""Tree-classification for tool definitions.

Each tool lives in a tree branch (``tool``, ``spec-read``, ``spec-write``,
``db``, plus the deployment-specific ``s3df``/``s3df psql``, ``spec-file``,
and ``slack`` branches added in Phase 2).

The classification follows this precedence:

1. ``CATEGORY_OVERRIDES`` — an explicit per-tool-name override (used to
   move file-cache scan tools out of ``tool`` and into ``spec-file``
   without touching every definition entry).
2. The tool definition's own ``"tree"`` field (a string like ``"s3df"``
   or a dotted path like ``"s3df.psql"`` for sub-branches).
3. Lineage-driven rules (preserved from the original implementation):
   ``autonomy_db`` source → ``db``; requires ``justification`` →
   ``spec-write``; ``spec_command`` set → ``spec-read``; otherwise →
   ``tool``.

Lives in ``tool_catalog/`` (not ``cli/``) so both the CLI parser and the
DISPATCH builder can import without a circular dependency.
"""
from __future__ import annotations

from beamtimehero_cli.tool_catalog.lineage import TOOL_LINEAGE


# Tool name → category override. Used to relocate tools whose default
# classification doesn't match the desired branch layout. Each value is
# either a top-level branch name (``"spec-file"``) or a dotted path for
# nested branches (``"s3df.psql"``).
#
# File-cache scan tools historically lived under ``tool`` because they
# fit no other branch. With the ``spec-file`` branch added we move them
# here without touching every individual definition entry.
CATEGORY_OVERRIDES: dict[str, str] = {
    "list_scans": "spec-file",
    "get_latest_scan": "spec-file",
    "read_scan": "spec-file",
    "get_active_counter": "spec-file",
    "get_scan_deadtime": "spec-file",
    "normalize_scan": "spec-file",
    "average_scans": "spec-file",
    "plot_scan": "spec-file",
    "plot_averaged_scans": "spec-file",
    "plot_scan_stack": "spec-file",
    "plot_first_half_vs_second_half": "spec-file",
    "plot_running_average": "spec-file",
    "plot_feature_evolution": "spec-file",
    "group_scans_by_spot": "spec-file",
    "analyze_per_spot": "spec-file",
    "analyze_convergence": "spec-file",
    "analyze_efficiency": "spec-file",
    "analyze_feature_evolution": "spec-file",
}


def categorize(tool_def: dict) -> tuple[str, ...]:
    """Return the tree path a tool belongs to as a tuple of segments."""
    name = tool_def.get("function", {}).get("name", "")

    # Explicit ``tree`` field on the definition wins over everything —
    # it's the most specific signal and lets two definitions sharing a
    # name (e.g. spec-file/list_scans + s3df/list_scans) coexist.
    explicit = tool_def.get("tree")
    if explicit:
        return _split(explicit) if isinstance(explicit, str) else tuple(explicit)

    # Per-name overrides apply only to definitions that don't pin their
    # own tree — used to move the file-cache scan tools out of "tool"
    # without touching each entry.
    if name in CATEGORY_OVERRIDES:
        return _split(CATEGORY_OVERRIDES[name])

    lineage = TOOL_LINEAGE.get(name) or {}
    if lineage.get("source") == "autonomy_db":
        return ("db",)

    params = tool_def.get("function", {}).get("parameters", {}) or {}
    required = set(params.get("required", []) or [])
    if "justification" in required:
        return ("spec-write",)

    if lineage.get("spec_command") is not None:
        return ("spec-read",)

    return ("tool",)


def _split(tree: str) -> tuple[str, ...]:
    """Parse a dotted-path tree string into a tuple of segments."""
    return tuple(s for s in tree.split(".") if s)
