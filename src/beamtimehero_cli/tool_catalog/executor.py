"""Tool executor — dispatches tool calls to handler implementations.

Returns ``(result_text, images_b64)`` for each tool invocation.

DISPATCH is keyed by ``(tree, ..., name)`` tuples so the same leaf name
can exist under multiple branches (e.g. ``("spec-file", "list_scans")``
and ``("s3df", "list_scans")``). Callers pass the tree along with the
name — a 1-tuple like ``("tool",)`` for top-level branches, or longer
like ``("s3df", "psql")`` for nested branches.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def execute_tool(
    tree: tuple[str, ...] | str,
    name: str,
    arguments: dict,
) -> tuple[str, list[str]]:
    """Execute a tool by ``(tree, name)`` with arguments.

    ``tree`` may be a single string (single-segment branch) or a tuple
    of segments (for nested branches).
    """
    try:
        from beamtimehero_cli.tool_catalog.tools_core import DISPATCH
    except Exception:
        DISPATCH: dict = {}

    key_path = (tree,) if isinstance(tree, str) else tuple(tree)
    key = key_path + (name,)
    fn = DISPATCH.get(key)
    if fn is None:
        return f"Unknown tool: {'/'.join(key)}", []
    try:
        text, imgs = fn(arguments or {})
        return text, list(imgs or [])
    except Exception as e:
        logger.error("Tool %s failed: %s", "/".join(key), e, exc_info=True)
        return f"Tool error ({'/'.join(key)}): {e}", []
