# beamtimehero_cli

Generic command-line interface for the SSRL BL15-2 beamline.

Provides:

- **SPEC injection** — motor moves, scans, macro execution against a SPEC server (TCP, GNU screen, or sandbox/mock transports).
- **Scan data reads** — direct silx-based SPEC file parsing, scan analysis, plotting.
- **Log reads** — beamline control log parsing, search.
- **Action logging** — every command writes to a local SQLite audit trail.
- **Reference docs** — `beamtimehero ref <name>` to fetch bundled procedure docs.

This is the generic CLI surface. It does not include experiment-planning,
orchestrator, or agent-harness concepts — those live in consuming projects.

## Install

```bash
pip install -e .
```

## Quick start

```bash
beamtimehero --help
beamtimehero ref --list
beamtimehero tool list-scans --limit 5
SPEC_MOCK=1 beamtimehero spec-read get-beam-status
```

## CLI surface

```
beamtimehero ref [--list | <name>]      # bundled reference docs
beamtimehero tool <command>             # non-SPEC tools (data, logs, plots)
beamtimehero db <command>               # action-log queries
beamtimehero spec-read <command>        # SPEC-bound reads (no mutation)
beamtimehero spec-write <command>       # SPEC-bound mutations (--justification required)
```

Discover leaves with `--help` at any depth.

## Env vars

| Var | Default | Meaning |
|---|---|---|
| `SPEC_MOCK` | `1` | If `1`, route SPEC commands to the mock backend. Set to `0` on the beamline host. |
| `SPEC_TRANSPORT` | `tcp` | One of `tcp`, `screen`, `sandbox`. |
| `SPEC_HOST` | `localhost` | TCP transport target. |
| `SPEC_PORT` | `2033` | TCP transport port. |
| `SPEC_EVAL_URL` | `http://127.0.0.1:5006` | Sandbox transport endpoint. |
| `BL_SCAN_DIR` | `/data/fifteen` | Scan file root. Auto-detects the most recent `YYYY-mm_*` subdir if the root itself isn't dated. |
| `BL_LOGS_DIR` | `/usr/local/lib/spec.log/logfiles` | Control log file directory. |
| `BEAMLINE_TOOLS_DB_PATH` | `data/beamline_tools.db` | SQLite path for the action log. |
| `BEAMTIMEHERO_CLI_LOG` | `1` | If `1`, log each CLI invocation. |
| `BEAMTIMEHERO_CLI_LOG_MAX_BYTES` | `65536` | Stdout tail bytes captured per invocation. |
