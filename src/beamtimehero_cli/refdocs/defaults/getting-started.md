# beamtimehero CLI — getting started

```
beamtimehero ref [--list | <name>]      # reference docs
beamtimehero tool <command>             # non-SPEC tools (data, logs, plots)
beamtimehero db <command>               # action-log queries
beamtimehero spec-read <command>        # SPEC-bound reads
beamtimehero spec-write <command>       # SPEC-bound mutations (requires --justification)
beamtimehero spec-file <command>        # scan reads + XAS/HERFD analysis over SPEC files on disk
beamtimehero xrs <command>              # X-ray Raman analysis (energy-loss axis)
beamtimehero exafs <command>            # EXAFS k-space analysis (chi(k), Fourier transforms)
beamtimehero s3df <command>             # S3DF deployment backend (Postgres + pickled scans)
beamtimehero s3df psql <command>        # read-only SQL against the S3DF Postgres
beamtimehero slack <command>            # Slack messaging
```

Agent profiles (curated alias views, e.g. `bl-aligner`) are listed with
`beamtimehero --list-profiles`.

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
