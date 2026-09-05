"""The generated science index must stay in step with the source tree."""
from __future__ import annotations

from beamtimehero_cli import docgen_science as dg


def test_scan_finds_the_science_package():
    data = dg.scan()
    sci = {k: v for k, v in data["modules"].items() if v["is_science"]}
    assert len(sci) > 25, "science/ modules should be discovered"
    # every science module is either a package __init__ or carries functions
    assert any(m["functions"] for m in sci.values())


def test_every_public_science_function_is_listed():
    data = dg.scan()
    page = dg.render()
    for dotted, m in data["modules"].items():
        if not m["is_science"]:
            continue
        for name, fn in m["functions"].items():
            if not fn["private"]:
                assert name in page, f"{dotted}.{name} missing from the index"


def test_reverse_index_reaches_the_science_core():
    """The 'used by' column is the point of the page — it must resolve."""
    data = dg.scan()
    rev = dg.reverse_index(data)
    sci_fns = {(m, f) for m, mm in data["modules"].items()
               if mm["is_science"] for f in mm["functions"]}
    reached = set(rev) & sci_fns
    assert len(reached) / len(sci_fns) > 0.8, (
        f"only {len(reached)}/{len(sci_fns)} science functions reachable from a "
        "tool — the call graph probably broke"
    )
    # a known deep chain: handler -> descriptors -> fits
    assert any(f == "fit_white_line" for _m, f in rev)


def test_citations_are_collected_and_gaps_flagged():
    data = dg.scan()
    cites = {k: v for m in data["modules"].values() if m["is_science"]
             for k, v in m["citations"].items()}
    assert len(cites) > 20, "CITATIONS dicts should be picked up"
    assert any(v is None for v in cites.values()), "gaps should be representable"
    assert any(v and "Wilke" in v for v in cites.values())


def test_every_science_module_declares_citations():
    """An absent CITATIONS dict must not be quieter than an empty one.

    ``science/README.md`` says every module implementing published methods
    declares a module-level ``CITATIONS`` dict, and the index turns ``None``
    values into a visible to-do list. But a *missing* dict contributed nothing
    to that list, so the two states read identically from the outside while
    meaning opposite things — "nothing to attribute" and "nobody looked".

    ``{}`` is a valid answer, and the modules that use it say why in a comment
    above it: ``science/plots/*`` render results computed elsewhere. What is
    not valid is silence.
    """
    data = dg.scan()
    missing = sorted(
        dotted for dotted, m in data["modules"].items()
        if m["is_science"] and m["functions"] and not m["declares_citations"]
    )
    assert not missing, (
        "science modules with no CITATIONS dict: " + ", ".join(missing) + ".\n"
        "Add one — `None` is the honest value for a method you have not "
        "attributed, and an empty dict is right for a module that implements "
        "no method of its own. See the Conventions section of "
        "science/README.md."
    )


def test_render_is_self_contained_html():
    page = dg.render()
    assert page.startswith("<!DOCTYPE html>")
    assert page.rstrip().endswith("</html>")
    for needle in ("<style>", "science/tables/", "Bibliography", "needs a reference"):
        assert needle in page
    assert "src=" not in page, "page must not reference external assets"
