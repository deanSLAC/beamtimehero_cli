"""Every tool definition must be fully wired: a handler and a lineage entry.

``CONTRIBUTING.md`` blesses adding a tool as additive and needing no
permission, which makes it the contribution most likely to arrive half-wired.
Nothing caught that before: a definition with no handler reaches the agent
through ``--help`` and then answers "Unknown tool" at runtime, and a definition
with no lineage entry is absent from ``docs/tool_catalog.html`` while
``categorize.py`` silently falls back to ``{}`` and puts it in whatever branch
the default rule picks.

Both halves pass with no exemptions: every one of the 125 definitions has a
handler and a lineage entry. Keep it that way — an exemption list here would
just recreate the gap.
"""
from __future__ import annotations

import pytest

from beamtimehero_cli.tool_catalog import TOOL_DEFINITIONS
from beamtimehero_cli.tool_catalog.lineage import TOOL_LINEAGE
from beamtimehero_cli.tool_catalog.tools_core import DISPATCH, _HANDLERS



def _tool_names():
    return sorted(d["function"]["name"] for d in TOOL_DEFINITIONS)


@pytest.mark.parametrize("name", _tool_names())
def test_every_definition_has_a_handler(name):
    """Without this, a new tool parses and then fails at dispatch time."""
    reachable = set(_HANDLERS) | {key[-1] for key in DISPATCH}
    assert name in reachable, (
        f"tool {name!r} is in definitions.py but has no handler. Add "
        f"t_{name}(arguments) -> (text, images_b64) to tools_core.py and "
        "register it in _HANDLERS."
    )


@pytest.mark.parametrize("name", _tool_names())
def test_every_definition_has_a_lineage_entry(name):
    assert name in TOOL_LINEAGE, (
        f"tool {name!r} has no TOOL_LINEAGE entry, so it will not appear on "
        "docs/tool_catalog.html and categorize.py cannot use its source or "
        "spec_command to place it. Add one to tool_catalog/lineage.py."
    )



def test_no_lineage_entry_without_a_definition():
    orphans = set(TOOL_LINEAGE) - set(_tool_names())
    assert not orphans, (
        f"lineage entries with no tool definition: {sorted(orphans)}"
    )


def test_every_lineage_source_is_a_documented_value():
    """The source badge groups the catalog page; an undocumented value colours
    nothing and tells an operator nothing."""
    documented = {
        "spec_datafile", "spec_session", "spec_logfile", "spec_config",
        "autonomy_db", "filesystem", "tool_chain", "postgres", "camera",
        "slack",
    }
    unknown = {}
    for name, entry in TOOL_LINEAGE.items():
        src = entry.get("source")
        if src not in documented:
            unknown.setdefault(src, []).append(name)
    assert not unknown, (
        f"undocumented lineage source values: { {k: sorted(v) for k, v in unknown.items()} }. "
        "Add the value to the enum in tool_catalog/lineage.py's docstring and to "
        "this set, or use an existing one."
    )


def test_every_lineage_entry_is_complete():
    """A half-filled entry renders as blank fields on the catalog page."""
    required = ("long_description", "python_func", "output", "source",
                "source_detail", "depends_on")
    incomplete = {
        name: [f for f in required if not entry.get(f) and f != "depends_on"]
        for name, entry in TOOL_LINEAGE.items()
    }
    incomplete = {k: v for k, v in incomplete.items() if v}
    assert not incomplete, f"lineage entries with empty fields: {incomplete}"


# Prerequisites that live in the consuming applications rather than this
# catalog. The orchestrator tools are deliberately absent here — test_smoke.py
# asserts they never leak in — but a tool whose real precondition is "the app
# has transitioned into this phase" should still say so, so these are allowed
# by name rather than silently dropped.
CONSUMER_APP_TOOLS = {"transition_phase", "get_plan"}


def test_depends_on_names_a_real_tool_or_a_known_consumer_tool():
    """A prerequisite that exists nowhere is worse than none — it sends an
    agent looking for a tool it cannot call. Cross-app prerequisites are
    legitimate; typos and renames are not."""
    known = set(_tool_names()) | CONSUMER_APP_TOOLS
    bad = {
        n: [d for d in (e.get("depends_on") or []) if d not in known]
        for n, e in TOOL_LINEAGE.items()
    }
    bad = {k: v for k, v in bad.items() if v}
    assert not bad, (
        f"depends_on referencing tools that exist neither in this catalog nor "
        f"in CONSUMER_APP_TOOLS: {bad}"
    )
