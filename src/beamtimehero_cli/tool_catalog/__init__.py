"""beamtimehero_cli tool catalog.

Public surface:

  * ``TOOL_DEFINITIONS`` — JSON-schema definitions for every tool.
  * ``TOOL_CATEGORIES`` — UI groupings.
  * ``CLI_TOOL_DEFINITION`` — single-tool wrapper for progressive discovery mode.
  * ``execute_tool(name, args)`` — dispatch to a tool's Python implementation.
"""
from __future__ import annotations

from beamtimehero_cli.tool_catalog.cli_tool import CLI_TOOL_DEFINITION
from beamtimehero_cli.tool_catalog.definitions import (
    AUTONOMY_TOOL_CATEGORIES as _BASE_CATEGORIES,
    AUTONOMY_TOOL_DEFINITIONS as _BASE_TOOLS,
)
from beamtimehero_cli.tool_catalog.executor import execute_tool

TOOL_DEFINITIONS: list[dict] = list(_BASE_TOOLS)
TOOL_CATEGORIES = list(_BASE_CATEGORIES)


__all__ = [
    "CLI_TOOL_DEFINITION",
    "TOOL_CATEGORIES",
    "TOOL_DEFINITIONS",
    "execute_tool",
]
