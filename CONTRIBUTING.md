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
has a right answer to check against. `tests/test_interpretation.py` is the
model to copy.

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
- **Two directories are currently unrouted** — `generic_data/fitter.py` and
  `experiment_planning/decisions.py` are not reachable from any tool. They look
  like the most scientific code in the repo but nothing calls them; don't be
  misled. Their fate is undecided.
