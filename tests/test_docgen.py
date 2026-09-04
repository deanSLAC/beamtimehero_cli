"""Docgen coverage: the generated catalog page must track the live registry."""
from beamtimehero_cli.docgen import BRANCH_NOTES, collect, first_sentence, render
from beamtimehero_cli.tool_catalog import TOOL_DEFINITIONS


def test_tool_count_matches_registry():
    cat = collect()
    assert len(cat["tools"]) == len(TOOL_DEFINITIONS)


def test_every_tool_rendered():
    page = render()
    for tdef in TOOL_DEFINITIONS:
        name = tdef["function"]["name"]
        assert f'<code class="tname">{name}</code>' in page, name


def test_no_downstream_orchestration_entries():
    # CAT-8 orchestration names are defined in downstream consumers, not
    # here — they must never appear as catalog entries. (Plain-text
    # depends_on references to them are fine.)
    page = render()
    for phantom in ("transition_phase", "update_plan", "get_staff_guidance"):
        assert f'<code class="tname">{phantom}</code>' not in page, phantom


def test_every_branch_has_a_note():
    # A new branch must ship with a human-facing blurb for the page.
    cat = collect()
    for tree, _ in cat["branches"]:
        assert tree in BRANCH_NOTES, f"missing BRANCH_NOTES entry for {tree}"


def test_first_sentence_heuristic():
    assert first_sentence("One. Two.") == "One."
    assert first_sentence("Uses e.g. windows. Next part.") == "Uses e.g. windows."
    assert first_sentence("No terminal punctuation") == "No terminal punctuation"
    assert first_sentence("") == ""
