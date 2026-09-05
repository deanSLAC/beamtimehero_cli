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


def test_render_is_self_contained_html():
    page = dg.render()
    assert page.startswith("<!DOCTYPE html>")
    assert page.rstrip().endswith("</html>")
    for needle in ("<style>", "science/tables/", "Bibliography", "needs a reference"):
        assert needle in page
    assert "src=" not in page, "page must not reference external assets"
