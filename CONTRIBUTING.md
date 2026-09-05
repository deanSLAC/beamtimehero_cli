# Contributing to beamtimehero_cli

This repo is a toolbelt: a flat catalog of ~130 tools that LLM agents call,
plus the science those tools run. Several applications depend on it, which
determines what is safe to change and what needs a conversation first.

## If you are contributing science

**Work in [`src/beamtimehero_cli/science/`](src/beamtimehero_cli/science/README.md).**
That directory has its own README with the layout, the one rule it follows, and
a "you want to change X → go to Y" table. Start there; you should not need to
read anything else in the repo.

Everything inside `science/` is fair game — normalization, fits, descriptors,
interpretation logic, the tabulated physics, the defaults in each
`policy.py`. That is the part of this project that should keep changing, and
you do not need permission to change it.

```bash
python3 -m venv venv && source venv/bin/activate
pip install -e '.[dev]'
python -m pytest                          # ~20s
python -m pytest tests/test_interpretation.py -q     # the science tests
```

The science tests build synthetic spectra with analytically known ground truth
(an erf edge + Gaussian pre-edge + Gaussian white line), so every descriptor
has a right answer to check against. By area:

| Area | Tests |
|---|---|
| XAS descriptors & interpretation | `tests/test_interpretation.py`, `tests/test_interpretation_tools.py` |
| Reduction (counters, reps, normalization) | `tests/test_analysis_xas.py` |
| EXAFS | `tests/test_analysis_exafs.py` |
| XRS | `tests/test_xrs.py` |
| Tool-level science | `tests/test_twocol_and_analysis_leaves.py` |
| Scientific defaults (pinned values) | `tests/test_science_policy.py` |

`tests/test_interpretation.py` is the clearest model for the synthetic-spectrum
pattern. Note that these files import through the **old** module paths
(`beamtimehero_cli.interpretation`, `.analysis`) on purpose: that makes the
suite double as a compatibility check on the re-export shims. **New tests
should import from `beamtimehero_cli.science.*`.**

The scientific defaults *are* pinned. `tests/test_science_policy.py` holds the
current value of every constant in every `policy.py`, and checks that the
science functions and the agent-facing tool schema both read from policy rather
than from a literal that merely agrees with it. So:

- Changing a default **will** fail that test. That is the point — update the
  expected value in the same commit, and the diff becomes the record of which
  physics default moved and why.
- Adding a *new* policy constant without pinning it also fails, with a message
  naming the constant.

To see the whole science surface at once — every function with its signature,
what calls it, and what it cites:

```bash
open docs/science_index.html                    # view
python -m beamtimehero_cli.docgen_science       # regenerate
```

The **"used by"** column on that page is the one worth knowing about: it is
computed from a call graph, so before changing a function you can see which
tools depend on it without tracing imports by hand.

If you add or change a published method, record the reference in that module's
`CITATIONS` dict. The index collects those into a bibliography and lists the
entries still marked `None` as attribution gaps — 22 of them today, and
filling one in is a genuinely useful first contribution.

## What to raise rather than edit

Three places define what the *agents* see. Changing them changes what several
separate applications see, so open an issue or ask first:

| File | Why |
|---|---|
| `tool_catalog/definitions.py` | the JSON schema for every tool — names, parameters, defaults |
| `tool_catalog/categorize.py` | which CLI branch each tool sits on |
| `cli/` | the parser and the agent profiles built over the catalog |

Concretely, these need a heads-up: **renaming a tool, adding or renaming a
parameter, changing a parameter's type, or moving a tool to a different
branch.** Adding a brand-new tool is fine — it is additive.

Changing what a tool *computes* is not on this list. That is science, and it
belongs in `science/`.

## Layering

```
tool_catalog/     JSON schema in, JSON + base64 PNG out. what the agent sees.
      ↑
spec_data/        backends: SPEC files, Postgres, SSRL collector. knows where data lives.
spec_control/     SPEC transports (tcp / screen / sandbox / mock).
      ↑
science/          arrays in, dicts out. no I/O, no env, no SPEC.
```

A tool handler in `tool_catalog/tools_core.py` should unpack the argument dict,
ask `spec_data` for arrays, call one science function, and serialise the
result. If you find yourself writing a scientific decision or a numpy
expression in a handler, it wants to be a named function in `science/`
instead — that is the boundary this repo is organized around.

## Practical notes

- **SPEC is mocked by default.** `SPEC_MOCK` defaults to `1`; nothing touches a
  beamline unless you set it to `0`.
- **Every mutating tool requires `--justification`** and writes to a SQLite
  audit trail. That is deliberate; don't route around it.
- **The human-readable tool catalog** is generated, not hand-written:
  `python -m beamtimehero_cli.docgen` regenerates `docs/tool_catalog.html`.
  Regenerate it after catalog changes rather than editing the HTML.
- **Two files are unrouted** — `generic_data/fitter.py` and
  `experiment_planning/decisions.py` are not reachable from any tool (the
  fitter only via `decisions.py`, which has no callers). They look like the
  most scientific code in the repo; nothing calls them. Their fate is undecided.
- **Some live science still sits outside `science/`.** Most of the
  array-taking plotting is in `spec_data/exafs_plotting.py`,
  `spec_data/xrs_plotting.py` and `spec_data/plotting.py` — by the rule those
  belong in `science/plots/`, but they have not moved. If your change is about
  what a plot looks like, look there too.
  (Scan statistics *have* moved: `experiment_planning/scan_features.py` and
  `scan_efficiency.py` are now `science/statistics/`, with shims left behind.)

## Background

`docs/architecture-review.html` is the analysis this layout came out of: why the
science was hard to find, the full destination map, and a status section listing
where the implementation diverged from the plan and what is still open. Read it
if you want the reasoning rather than the rules.
