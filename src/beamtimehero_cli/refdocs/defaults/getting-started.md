# beamtimehero CLI — getting started

```
beamtimehero ref [--list | <name>]      # reference docs
beamtimehero catalog [--tree|--profile] # export the tool schemas as JSON
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
beamtimehero spec-read read-motor-position --help
```

Driving this from an agent: `beamtimehero ref agent-integration`.

Environment variables of interest:

- `SPEC_MOCK=1` — route all SPEC calls to the mock backend. The default, so
  nothing reaches a beamline until you set it to `0`.
- `BL_SCAN_DIR` — scan file root. There is no bundled sample data; without this
  the scan tools report that no directory is configured.
- `SSRL_COLLECTOR_DIR` — directory of SSRL "EXAFS Data Collector" ASCII files,
  when that is the format you are reading instead of SPEC files.
- `BL_LOGS_DIR` — control log directory.
- `BEAMTIMEHERO_DATA_DIR` — writable state (the action log). Defaults to
  `<repo>/data` from a checkout, `~/.local/share/beamtimehero` when installed.
- `BEAMTIMEHERO_CONFIG` — path to a YAML config whose `env:` mapping is
  applied. `config.example.yaml` in the repository documents every variable,
  grouped by task, with defaults. Exported variables win over the file.

Every CLI invocation is recorded in the action log. See `beamtimehero ref action-log`.
