"""Every tool definition must be fully wired: a handler and a lineage entry.

``CONTRIBUTING.md`` blesses adding a tool as additive and needing no
permission, which makes it the contribution most likely to arrive half-wired.
Nothing caught that before: a definition with no handler reaches the agent
through ``--help`` and then answers "Unknown tool" at runtime, and a definition
with no lineage entry is absent from ``docs/tool_catalog.html`` while
``categorize.py`` silently falls back to ``{}`` and puts it in whatever branch
the default rule picks.

``LINEAGE_BACKLOG`` is a shrinking list, not a permanent exemption: the tools
that predate this test. Adding to it is not the fix.
"""
from __future__ import annotations

import pytest

from beamtimehero_cli.tool_catalog import TOOL_DEFINITIONS
from beamtimehero_cli.tool_catalog.lineage import TOOL_LINEAGE
from beamtimehero_cli.tool_catalog.tools_core import DISPATCH, _HANDLERS

# Tools that predate this test and still need a TOOL_LINEAGE entry. Delete
# names as they are backfilled; when this is empty, drop it and the skip below.
LINEAGE_BACKLOG = {
    "align_crystals", "analyze_feature_evolution", "analyze_per_spot",
    "assess_xas_quality", "assess_xrs_quality", "average_xrs_scans",
    "build_loss_axis", "calibrate_energy_loss", "compare_xrs_to_references",
    "detect_per_scan_drift", "exafs_products", "execute_readonly_sql",
    "extract_chi", "extract_xas_descriptors", "extract_xrs_descriptors",
    "find_edge_e0", "fit_xas_pre_edge", "fit_xas_white_line",
    "fourier_transform_chi", "get_energy_calibration", "group_scans_by_spot",
    "identify_edge", "interpret_coordination_geometry",
    "interpret_oxidation_state", "interpret_q_dependence",
    "interpret_xrs_oxidation_state", "list_channels", "list_collector_scans",
    "normalize_xas_intensity", "normalize_xrs", "overlay_chi_spectra",
    "overlay_xrs_spectra", "plot_feature_evolution",
    "plot_first_half_vs_second_half", "plot_running_average", "plot_scan_stack",
    "post_slack_message", "read_channel_messages", "read_thread_replies",
    "record_energy_calibration", "subtract_compton_background", "sum_crystals",
    "summarize_sample_chemistry", "summarize_xrs_chemistry", "tag_crystal_q",
}


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
    if name in LINEAGE_BACKLOG:
        pytest.skip("pre-existing lineage gap — see LINEAGE_BACKLOG")
    assert name in TOOL_LINEAGE, (
        f"tool {name!r} has no TOOL_LINEAGE entry, so it will not appear on "
        "docs/tool_catalog.html and categorize.py cannot use its source or "
        "spec_command to place it. Add one to tool_catalog/lineage.py."
    )


def test_lineage_backlog_has_no_stale_names():
    """A backlog that outlives its entries starts exempting live tools."""
    unknown = LINEAGE_BACKLOG - set(_tool_names())
    assert not unknown, (
        f"LINEAGE_BACKLOG names tools that no longer exist: {sorted(unknown)}. "
        "Remove them."
    )
    done = LINEAGE_BACKLOG & set(TOOL_LINEAGE)
    assert not done, (
        f"these tools now have lineage entries: {sorted(done)}. Remove them "
        "from LINEAGE_BACKLOG so the test guards them."
    )


def test_no_lineage_entry_without_a_definition():
    orphans = set(TOOL_LINEAGE) - set(_tool_names())
    assert not orphans, (
        f"lineage entries with no tool definition: {sorted(orphans)}"
    )
