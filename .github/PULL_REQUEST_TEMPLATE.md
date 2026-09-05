## What this changes

<!-- One or two sentences. Why, not what — the diff says what. -->

## Checklist

- [ ] `python -m pytest` and `ruff check src tests` pass locally — CI runs
      both, lint first.
- [ ] If a `policy.py` constant moved, its pinned value in
      `tests/test_science_policy.py` is updated in this same commit.
- [ ] If an *unpinned* default moved — the inline ones in `exafs/fourier.py`,
      `xas/normalize.py`, `xrs/reduce.py`, `fitting/similarity.py` — the commit
      message says so, because no test will. (`reduce/` and `statistics/` are
      pinned; they belong to the box above.)
- [ ] If a published method was added or changed, its `CITATIONS` entry is
      recorded (`None` is a valid, tracked answer; inventing a reference is not).
- [ ] Generated docs regenerated if the source they describe changed:
      `python -m beamtimehero_cli.docgen_science`, `python -m beamtimehero_cli.docgen`.

## Agent-facing surface

Five sibling applications consume this catalog, so these changes need a
heads-up before merge — tick if the PR touches any:

- [ ] `tool_catalog/definitions.py` — renaming a tool, adding/renaming a
      parameter, or changing a parameter's type
- [ ] `tool_catalog/categorize.py` — moving a tool to a different branch
- [ ] `cli/` — the parser or the agent profiles

Adding a brand-new tool is additive and does not need this — see
"Adding a tool" in [CONTRIBUTING.md](../CONTRIBUTING.md).
