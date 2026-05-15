# Action log

Every `beamtimehero` invocation is recorded to a local SQLite file
(default: `$BEAMLINE_TOOLS_DB_PATH`, falling back to
`data/beamline_tools.db` relative to the package).

Tables:

- **CliInvocationLog** — one row per CLI process: argv, parsed tree/leaf,
  tool name, justification, exit code, latency, captured stdout tail,
  agent role (if invoked under an agent scope), spec_mock flag, pid.
- **ActionLog** — one row per SPEC injection: command + args, justification,
  start/finish timestamps, success flag, result text.
- **QueryLog** — one row per read-only SPEC query.

Disable invocation logging with `BEAMTIMEHERO_CLI_LOG=0`. Cap captured stdout
size with `BEAMTIMEHERO_CLI_LOG_MAX_BYTES` (default 65536).

The DB is created on first use. Concurrent writes from multiple processes
work in SQLite's default mode for this workload.
