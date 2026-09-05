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

Three environment variables get you running; `config.example.yaml` in the
repository is the authoritative list of all of them, grouped by task, with
defaults.

- `SPEC_MOCK` — `1` (the default) routes every SPEC call to the mock backend,
  so nothing reaches a beamline. The test is for the exact string `1`; any
  other value goes live, so quote it in YAML.
- `BL_SCAN_DIR` — scan file root. There is no bundled sample data; without this
  the scan tools report that no directory is configured.
- `BEAMTIMEHERO_CONFIG` — path to a YAML config whose `env:` mapping is
  applied. Exported variables win over the file.

Every CLI invocation is recorded in the action log. See `beamtimehero ref action-log`.
