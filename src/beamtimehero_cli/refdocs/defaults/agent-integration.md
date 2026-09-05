# Using beamtimehero from an agent

This CLI exists to be driven by an LLM agent. The nested `--help` surface, the
JSON-only output, and the audit trail are all shaped around that. This doc is
how you wire one up.

## The two modes

**Progressive discovery (default).** Give the agent one tool that runs
`beamtimehero <args>` and let it explore with `--help`. This is what
`TOOLS_MODE=cli` — the default — means, and it is the right choice for a
general coding agent or anything with shell access. The agent sees a small
surface and drills down only where it needs to.

**Full schema registration.** Hand the agent all 131 tool schemas up front.
Right for a purpose-built harness where the agent should not spend turns on
discovery. Consuming applications set `TOOLS_MODE` to switch to this.

Get the schemas with:

```bash
beamtimehero catalog                        # every tool, JSON-schema form
beamtimehero catalog --tree exafs           # one branch
beamtimehero catalog --profile bl-aligner   # one agent profile's surface
beamtimehero catalog --names-only           # just the names
beamtimehero catalog --indent 0             # one line, for piping
```

The output is a list of `{"type": "function", "function": {name, description,
parameters}}` entries — the shape most harnesses already accept. Nothing about
it is Python-specific.

## Why this is safe to hand an agent

Four properties, all deliberate. They are the reason you can let a model drive
this without supervising every call:

- **Nothing reaches a beamline unless you say so.** `SPEC_MOCK` defaults to
  `1`. Every SPEC command answers from the mock backend until you set it to
  `0`. An agent exploring on a laptop cannot move a motor.
- **Mutations require a reason.** Every leaf under `spec-write` requires
  `--justification`, and refuses to run without it.
- **Everything is recorded.** Each invocation is written to a SQLite action
  log — argv, tool, justification, exit code, latency, stdout tail. See
  `beamtimehero ref action-log`.
- **Failures come back as JSON, not tracebacks.** A bad argument returns
  `{"ok": false, "error": "argparse: ..."}` on stdout. An agent can read and
  correct that; a stack trace on stderr it usually cannot.

## Mode 1: subprocess

Register one tool. The schema ships in the package as
`tool_catalog.CLI_TOOL_DEFINITION`, or write your own equivalent:

```json
{
  "name": "run_command",
  "description": "Run a beamtimehero CLI command. Start with 'beamtimehero --help' to discover the command tree; use '--help' at any depth for a specific command's options.",
  "parameters": {
    "type": "object",
    "properties": {
      "command": {
        "type": "string",
        "description": "Full command, e.g. 'beamtimehero spec-file list-scans --limit 5'"
      }
    },
    "required": ["command"]
  }
}
```

Then let the agent work down the tree:

```bash
beamtimehero --help                              # the branches
beamtimehero spec-file --help                    # leaves on one branch
beamtimehero spec-file extract-xas-descriptors --help
```

Point the agent at `docs/tool_catalog.html` if it can read files — that is the
whole surface on one page, with parameters and backend lineage.

### From Claude Code

There is no MCP server yet, so allow the command and let Claude use Bash.
In `.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "Bash(beamtimehero --help)",
      "Bash(beamtimehero ref:*)",
      "Bash(beamtimehero catalog:*)",
      "Bash(beamtimehero spec-file:*)",
      "Bash(beamtimehero xrs:*)",
      "Bash(beamtimehero exafs:*)",
      "Bash(beamtimehero spec-read:*)"
    ]
  }
}
```

Those are the read-only and analysis branches. Leave `spec-write` off the
allowlist so beamline mutations stay a per-call decision, even with
`SPEC_MOCK=1`.

## Mode 2: in-process

```python
from beamtimehero_cli.tool_catalog import TOOL_DEFINITIONS, execute_tool

# Whatever your harness registers tools from.
schemas = TOOL_DEFINITIONS

# Dispatch by (tree, name). The tree is a tuple because the same leaf name
# exists on more than one branch — ("spec-file", "list_scans") reads SPEC
# files, ("s3df", "list_scans") reads Postgres.
text, images_b64 = execute_tool(("spec-file",), "list_scans", {"limit": 5})

print(text)                  # JSON string
for b64 in images_b64:       # base64 PNGs, when the tool produced figures
    ...
```

`execute_tool` returns `(result_text, images_b64)` and does not raise: an
unknown tool comes back as `"Unknown tool: ..."`, and a tool that fails comes
back as `"Tool error (...): ..."`. Scientific functions raise `ValueError` on
data that cannot support the analysis, and the handlers turn that into a JSON
`error` field — so an agent gets a sentence it can act on instead of an
exception.

## What an agent will hit first

**No data.** With nothing configured, the scan and log tools report that no
directory is set:

```json
{"scans": [], "error": "No scan directory configured: BL_SCAN_DIR=... ",
 "scan_dir_configured": false}
```

There is no bundled sample data in this package. Set `BL_SCAN_DIR` to a real
scan root (or `SSRL_COLLECTOR_DIR` for SSRL Data Collector files) before
expecting scan tools to return anything. The SPEC tools work regardless, from
the mock backend.

**Configuration.** Everything resolves from environment variables.
`config.example.yaml` in the repository lists all of them, grouped by what you
are trying to do, with defaults. Point the CLI at a copy:

```bash
export BEAMTIMEHERO_CONFIG=/path/to/config.yaml
```

Exported variables always win over the file, so a checked-in baseline plus
per-host overrides works.

**Plot files.** Tools that draw figures return base64 PNGs; the CLI also writes
them to disk and reports the path. That defaults to `./data/tool_plots` under
the working directory — set `BEAMTIMEHERO_PLOTS_DIR` if you do not want them
landing wherever the agent happened to run.

## A first session, end to end

```bash
beamtimehero --help                                   # what exists
beamtimehero ref --list                               # the reference docs
beamtimehero catalog --names-only | head -20          # the tool names
SPEC_MOCK=1 beamtimehero spec-read get-beam-status    # a real answer, no beamline
beamtimehero spec-file list-scans --limit 5           # needs BL_SCAN_DIR
```

Every one of those runs with no configuration. The last returns the
"not configured" report until you set a scan directory, which is the honest
answer rather than an empty list.
