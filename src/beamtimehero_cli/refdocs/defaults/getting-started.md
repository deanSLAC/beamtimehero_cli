# beamtimehero CLI — getting started

```
beamtimehero ref [--list | <name>]      # reference docs
beamtimehero tool <command>             # non-SPEC tools (data, logs, plots)
beamtimehero db <command>               # action-log queries
beamtimehero spec-read <command>        # SPEC-bound reads
beamtimehero spec-write <command>       # SPEC-bound mutations (requires --justification)
```

Use `--help` at any depth to discover what's available:

```
beamtimehero --help
beamtimehero tool --help
beamtimehero spec-read motor-pos --help
```

Environment variables of interest:

- `SPEC_MOCK=1` — route all SPEC calls to the mock backend (safe default off-beamline).
- `BL_SCAN_DIR` — scan file root.
- `BL_LOGS_DIR` — control log directory.
- `BEAMLINE_TOOLS_DB_PATH` — action-log SQLite path.

Every CLI invocation is recorded in the action log. See `beamtimehero ref action-log`.
