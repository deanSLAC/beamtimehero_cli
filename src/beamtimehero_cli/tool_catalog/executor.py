"""Tool executor — dispatches tool calls to handler implementations.

Returns (result_text, images_b64) for each tool invocation.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def execute_tool(name: str, arguments: dict) -> tuple[str, list[str]]:
    """Execute a named tool with arguments. Returns (result_text, images_b64)."""
    try:
        from beamtimehero_cli.tool_catalog.tools_core import DISPATCH
    except Exception:
        DISPATCH = {}
    fn = DISPATCH.get(name)
    if fn is None:
        return f"Unknown tool: {name}", []
    try:
        text, imgs = fn(arguments or {})
        return text, list(imgs or [])
    except Exception as e:
        logger.error("Tool %s failed: %s", name, e, exc_info=True)
        return f"Tool error ({name}): {e}", []
