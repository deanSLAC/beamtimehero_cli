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
python -m pytest                          # 309 tests, ~25s
python -m pytest tests/test_interpretation.py -q     # the science tests
```

Python 3.11 or newer for development — that is what CI gates on. `pyproject.toml`
declares a 3.9 floor, but nothing has ever exercised it; CI runs a 3.9 job that
reports without blocking, so if you see it red the fix is to raise the declared
floor, not to chase it. Two optional extras exist and are not in `dev`: install `.[slack]`
if you are touching `notify/slack.py`, `.[postgres]` for
`spec_data/postgres_backend.py`. Both are imported lazily, so a bare install
runs fine without them.

Run every command in this file from the repository root — the `docgen` entry
points read and write paths relative to the working directory. `open` is
macOS; substitute `xdg-open` or your browser elsewhere.

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
| The `science/` boundary itself | `tests/test_science_boundary.py` |

`tests/test_interpretation.py` is the clearest model for the synthetic-spectrum
pattern. Note that these files import through the **old** module paths
(`beamtimehero_cli.interpretation`, `.analysis`) on purpose: that makes the
suite double as a compatibility check on the re-export shims. **New tests
should import from `beamtimehero_cli.science.*`.**

The scientific defaults *are* pinned. `tests/test_science_policy.py` holds the
current value of every constant in every `policy.py`, and checks that the
science functions and the agent-facing tool schema both read from policy rather
than from a literal that merely agrees with it. So:

- Changing a constant in `xas/`, `exafs/` or `xrs/` `policy.py` **will** fail
  that test. That is the point — update the expected value in the same commit,
  and the diff becomes the record of which physics default moved and why.
- Adding a *new* policy constant without pinning it also fails, with a message
  naming the constant.

`reduce/` and `statistics/` have a `policy.py` too now, so the glitch
threshold, the convergence and drift thresholds, and the repetition-efficiency
threshold are pinned alongside the technique defaults. The test discovers
`science/*/policy.py` by globbing rather than naming modules, so a new one is
covered by existing.

One edge remains: several numeric defaults still sit inline in the *technique*
modules without being in that technique's `policy.py` — the FT grid in
`exafs/fourier.py` (`nfft`, `kstep`, `rmax_out`), the first-shell search window,
the MBACK polynomial order and gaps in `xas/normalize.py`, the outlier-rejection
cuts in `xrs/reduce.py`. Nothing fails if you change those. If you touch one,
say so in the commit message yourself, and consider promoting it.

Two further tests, `tests/test_science_boundary.py`, assert that `science/`
imports nothing else from `beamtimehero_cli` and reads no environment,
filesystem or network. If you need data loaded, take it as an argument and let
`spec_data/` load it.

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
entries still marked `None` as attribution gaps; `docgen_science` prints the
running count when it regenerates. Filling one in is a genuinely useful first
contribution.

## What to raise rather than edit

Three places define what the *agents* see. Changing them changes what several
separate applications see, so open an issue
([deanSLAC/beamtimehero_cli/issues](https://github.com/deanSLAC/beamtimehero_cli/issues))
or ask a maintainer first:

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

## Adding a tool

Additive, so it needs no permission — but it does touch two of the three files
above, and there are five steps rather than the obvious two:

1. **`tool_catalog/lineage.py`** — a `TOOL_LINEAGE` entry: `long_description`,
   `python_func` (the call chain, so an operator can trace a call to its
   implementation), `spec_command` (`None` if it never touches SPEC), `output`,
   `source`. This feeds `docs/tool_catalog.html` *and* the fallback
   classification rules in `categorize.py`, so a tool without one is invisible
   on the catalog page and lands in whatever branch the default rule picks.
2. **`tool_catalog/definitions.py`** — the JSON schema the agent sees. Read
   every scientific default from the relevant `policy.py` rather than writing
   the literal (see `_exafs_policy.DEFAULT_KMIN` in the `fourier_transform_chi`
   entry); `tests/test_science_policy.py` asserts the schema and the science
   function agree, and a literal that merely *matches* fails it.
3. **`tool_catalog/tools_core.py`** — a handler `t_<name>(arguments)` returning
   `(text, images_b64)`, registered in `_HANDLERS`. `_build_dispatch()` keys it
   by `(tree, name)`, so the same leaf name can exist under two branches with
   different handlers. Keep it thin, per the layering rule below: unpack, ask
   `spec_data` for arrays, call one science function, serialise. `ValueError`
   from `science/` is the one error path — let it propagate to the handler's
   JSON error envelope rather than catching it deeper.
4. **`tool_catalog/categorize.py`** — only if the tool needs a branch the
   precedence rules would not give it. Prefer a `"tree"` field on the
   definition over an entry in `CATEGORY_OVERRIDES`.
5. **`python -m beamtimehero_cli.docgen`** to regenerate `docs/tool_catalog.html`.

`tests/test_tool_catalog_wiring.py` checks all of this: every definition has a
handler and a complete lineage entry, every `source` is a documented enum
value, and every `depends_on` names a tool that actually exists. A half-wired
tool fails the suite rather than returning "Unknown tool" at runtime.

## Commits

Commit subjects follow `area: lowercase imperative summary` — `science:`,
`tests:`, `docs:`, `spec_data:`, `exafs:` — with a body explaining why, not
what. Two content rules matter more than the format:

- Changing a `policy.py` constant means updating its pinned value in
  `tests/test_science_policy.py` **in the same commit**. That diff is the
  record of which physics default moved and when.
- Changing a default that *isn't* pinned — the ones in `reduce/`, `statistics/`
  and `fitting/` — means saying so in the commit message yourself, since no
  test will say it for you.

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
- **The plotting split is done.** Figures that take arrays or a descriptor
  dict live in `science/plots/` (`exafs.py`, `xrs.py`, `xas.py`, `scan.py`).
  The six that load a scan by file name stay in `spec_data/plotting.py`. If
  your change is about what a plot looks like, `science/plots/` is almost
  certainly the place; old import paths still work via shims.

## Background

`docs/architecture-review.html` is the analysis this layout came out of: why the
science was hard to find, the full destination map, and a status section
recording where the implementation diverged from the plan. Read it if you want
the reasoning rather than the rules.

`docs/xrs-analysis-branch-plan.md` is the domain background for the XRS branch.
Its "why XRS can't reuse the XAS path" table is worth reading before you touch
anything under `science/xrs/` — the XAS defaults are not merely suboptimal on
the energy-loss axis, they are wrong by construction. Its module paths predate
the `science/` move; the header maps them.
