# beamtimehero_cli

Generic command-line interface for the SSRL BL15-2 beamline.

Provides:

- **SPEC injection** — motor moves, scans, macro execution against a SPEC server (TCP, GNU screen, or sandbox/mock transports).
- **Scan data reads** — direct silx-based SPEC file parsing, scan analysis, plotting.
- **Spectroscopy analysis** — XAS/HERFD descriptors and interpretation, X-ray Raman (energy-loss) reduction, EXAFS chi(k)/Fourier-transform products.
- **Deployment backends** — the same scan-read surface served from S3DF Postgres + pickled scan data; Slack messaging.
- **Log reads** — beamline control log parsing, search.
- **Action logging** — every command writes to a local SQLite audit trail.
- **Reference docs** — `beamtimehero ref <name>` to fetch bundled procedure docs.

This is the generic CLI surface. It does not include orchestrator or
agent-harness concepts — those live in consuming projects.

## Install

```bash
pip install -e .
```

## Quick start

Every command here works with no configuration:

```bash
beamtimehero --help                                   # the command tree
beamtimehero ref --list                               # bundled reference docs
beamtimehero catalog --names-only | head              # the tool names
SPEC_MOCK=1 beamtimehero spec-read get-beam-status    # a real answer, mock backend
```

`SPEC_MOCK` defaults to `1`, so nothing reaches a beamline until you set it to
`0`. Tools that read scan files need `BL_SCAN_DIR` pointed at a scan root —
there is no bundled sample data, and without it they report that no directory
is configured rather than returning an empty result:

```bash
BL_SCAN_DIR=/path/to/scans beamtimehero spec-file list-scans --limit 5
```

## Driving this from an agent

This CLI exists to be called by an LLM agent, so that path is documented
first-class: **[`beamtimehero ref agent-integration`](src/beamtimehero_cli/refdocs/defaults/agent-integration.md)**.
The short version — two modes:

**Progressive discovery** (the default, `TOOLS_MODE=cli`). Give the agent one
tool that runs `beamtimehero <args>` and let it explore with `--help`. Right
for a general coding agent or anything with shell access.

**Full schema registration.** Export every tool schema and register them up
front:

```bash
beamtimehero catalog                        # all tools, JSON-schema form
beamtimehero catalog --tree exafs           # one branch
beamtimehero catalog --profile bl-aligner   # one profile's surface
```

Or in-process:

```python
from beamtimehero_cli.tool_catalog import TOOL_DEFINITIONS, execute_tool
text, images_b64 = execute_tool(("spec-file",), "list_scans", {"limit": 5})
```

Four properties make this safe to hand a model, and they are why the surface
looks the way it does: SPEC is mocked by default; every `spec-write` leaf
requires `--justification`; every invocation lands in a SQLite audit log; and
argument errors come back as `{"ok": false, "error": ...}` on stdout rather
than a traceback on stderr. The refdoc covers all of it, plus a
`.claude/settings.json` allowlist for Claude Code.

## CLI surface

```
beamtimehero ref [--list | <name>]      # bundled reference docs
beamtimehero catalog [--tree|--profile] # export the tool schemas as JSON
beamtimehero tool <command>             # non-SPEC tools (data, logs, plots)
beamtimehero db <command>               # action-log queries
beamtimehero spec-read <command>        # SPEC-bound reads (no mutation)
beamtimehero spec-write <command>       # SPEC-bound mutations (--justification required)
beamtimehero spec-file <command>        # scan reads + XAS/HERFD analysis over SPEC files on disk
beamtimehero xrs <command>              # X-ray Raman analysis (energy-loss axis)
beamtimehero exafs <command>            # EXAFS k-space analysis (chi(k), Fourier transforms)
beamtimehero s3df <command>             # S3DF deployment backend (Postgres + pickled scans)
beamtimehero s3df psql <command>        # read-only SQL against the S3DF Postgres
beamtimehero slack <command>            # Slack messaging
```

Discover leaves with `--help` at any depth. Agent profiles (curated alias
views over the catalog, e.g. `bl-aligner`) are listed with
`beamtimehero --list-profiles`.

## Tool catalog (human-readable)

The nested `--help` surface is aimed at LLM agents. For humans there is a
generated one-page catalog — the full CLI tree plus an A–Z list of every tool
with descriptions, parameters, and backend lineage:

```bash
open docs/tool_catalog.html                 # view
python -m beamtimehero_cli.docgen           # regenerate after catalog changes
```

## Science index (for contributors)

The scientific core lives in `src/beamtimehero_cli/science/`, organized by
technique. Its own [README](src/beamtimehero_cli/science/README.md) has the
layout and the one rule it follows. For a generated index of every science
function — signature, what it does, **which tools reach it**, and what it
cites:

```bash
open docs/science_index.html                    # view
python -m beamtimehero_cli.docgen_science       # regenerate
```

See [CONTRIBUTING.md](CONTRIBUTING.md) before your first change, and
`docs/architecture-review.html` for why the layout is the way it is.

## Configuration

Everything resolves from environment variables.
**[`config.example.yaml`](config.example.yaml)** is the authoritative list of
them — all ~36, grouped by what you are trying to do (off-beamline use,
beamline data on disk, where this package writes, a live SPEC session, station
overrides, the S3DF Postgres deployment, Slack, LLM log-checking), each with
its default and what it is for.

Point the CLI at a copy and it applies them:

```bash
cp config.example.yaml config.yaml    # edit, then
export BEAMTIMEHERO_CONFIG=$PWD/config.yaml
```

Anything already exported wins over the file, so a checked-in baseline plus
per-host overrides works. A `.env` in the working directory is also loaded
automatically. `tests/test_config_surface.py` asserts every variable the code
reads appears in that file, so it cannot drift.

The handful you are most likely to need:

| Var | Default | Meaning |
|---|---|---|
| `SPEC_MOCK` | `1` | Route SPEC commands to the mock backend. Set to `0` only on the beamline host. |
| `BL_SCAN_DIR` | `/data/fifteen` | Scan file root. Auto-detects the most recent `YYYY-mm_*` subdir if the root itself isn't dated. |
| `SSRL_COLLECTOR_DIR` | _(unset)_ | Directory of SSRL "EXAFS Data Collector" ASCII files. When set, the scan and EXAFS tools read that format. |
| `BL_LOGS_DIR` | `/usr/local/lib/spec.log/logfiles` | Control log directory. |
| `BEAMTIMEHERO_DATA_DIR` | `<repo>/data`, else `~/.local/share/beamtimehero` | Writable state: the action log, camera captures. A source checkout keeps it in the repo; an installed package uses the XDG user-data dir. |
| `BEAMTIMEHERO_PLOTS_DIR` | `./data/tool_plots` | Where tool PNGs are written. Relative to the working directory by default. |
| `BEAMTIMEHERO_CONFIG` | _(unset)_ | Path to a YAML config whose `env:` mapping is applied. |

## Extending the CLI

Consumers can compose their own subtrees on top of the upstream parser instead
of forking it. The helpers in `beamtimehero_cli.cli.__main__` are public:

| Name | Purpose |
|---|---|
| `build_parser()` | Build the default top-level parser (all canonical trees plus registered profiles). |
| `build_ref_subtree(subs)` | Mount only the `ref` subtree on an existing `_SubParsersAction`. |
| `build_catalog_subtrees(subs, tool_defs)` | Mount the catalog subtrees (`tool`, `db`, `spec-read`, `spec-write`, `spec-file`, `xrs`, `exafs`, `s3df`, `slack`, …) from a tool-definitions list (filtered or unfiltered). |
| `categorize(tool_def)` | Data-driven tree path for a tool def (e.g. `("spec-file",)`, `("s3df", "psql")`). |
| `add_arg(parser, key, prop, required)` | JSON-schema property → argparse flag. |
| `ToolParser` | `ArgumentParser` subclass that emits `{"ok": false, ...}` JSON on parse errors. |
| `run_ref(args)` | Dispatch a `ref` invocation. |
| `run_tool_leaf(args)` | Dispatch a catalog-leaf invocation. |
| `dispatch(parser, args)` | Top-level dispatcher (delegates to `run_ref` / `run_tool_leaf`). |
| `TeeStdout` | Stdout wrapper that captures a bounded tail (used by `main()` for CLI logging). |
| `run_with(parser_builder, dispatcher, argv=None, *, known_trees=None)` | Wrap a custom parser-builder + dispatcher with the same stdout-tee tail capture and `record_cli_invocation` CLI logging that `main()` provides. |
| `main(argv=None)` | Full standalone entry point — same as the `beamtimehero` console-script. |

Minimal composition example:

```python
import sys
from beamtimehero_cli import refdocs
from beamtimehero_cli.cli.__main__ import build_parser, dispatch

def main() -> int:
    refdocs.register_doc("my-procedure", "/path/to/my_doc.md", "Project-specific procedure")
    parser = build_parser()
    trees = parser._subparsers._group_actions[0]  # the top-level subparsers action
    my_tree = trees.add_parser("my-subtree", help="Project-specific subcommands")
    my_tree.add_argument("--foo")
    args = parser.parse_args()
    if args.tree == "my-subtree":
        print("foo =", args.foo)
        return 0
    return dispatch(parser, args)

if __name__ == "__main__":
    sys.exit(main())
```

The default `beamtimehero` console-script keeps working unchanged for any
consumer that doesn't extend it.
