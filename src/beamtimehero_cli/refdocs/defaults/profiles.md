# Agent profiles

An agent profile is a **curated view** over the master tool catalog,
exposed as its own top-level CLI branch. Profiles don't add tools; they
alias a chosen subset under a per-agent path so the agent sees one
clear, non-redundant surface.

## Why

The master catalog has multiple backend branches that serve the same
high-level operation (`spec-file list-scans` reads JSON+SPEC files;
`s3df list-scans` reads Postgres+pickles). An LLM agent shouldn't have
to know which backend it's on — its deployment decides. Profiles bake
that decision into the CLI surface.

## Discovery

```
beamtimehero --list-profiles
```

lists every registered profile and its alias count.

## How to invoke

```
beamtimehero <profile-name> <command> [args ...]
```

e.g.

```
beamtimehero k8s-agent list-scans --limit 5
beamtimehero k8s-agent execute-readonly-sql --query "SELECT 1"
beamtimehero bl-aligner read-scan --file-name xas.001 --scan-number 5
```

Every profile leaf accepts the same JSON-schema-derived arguments as its
canonical leaf, since both are built from the same tool definition.

## How to add a profile

Drop a new file in `src/beamtimehero_cli/cli/profiles/` exposing a
`PROFILE` dict:

```python
PROFILE = {
    "name": "my-agent",
    "description": "What this agent does and which backend it owns.",
    "aliases": {
        "list-scans":  ("s3df", "list_scans"),
        "plot-scan":   ("s3df", "plot_scan"),
        # nested branch:
        "execute-sql": ("s3df", "psql", "execute_readonly_sql"),
    },
}
```

Each value is the canonical `(tree, ..., name)` path in the master
catalog. The profile loader will warn and skip any alias that doesn't
resolve, so a typo doesn't break the whole CLI — but the agent will
silently not have access to that leaf, so check `--help` after editing.

## Constraints

- A profile name must **not** collide with a canonical tree
  (`ref`, `tool`, `db`, `spec-read`, `spec-write`, `spec-file`, `s3df`,
  `slack`). Collisions raise at parser build time.
- Profiles are a view, not an override. Canonical paths remain reachable
  unchanged.
- The kebab-case alias is the profile-side leaf name. The canonical
  catalog uses the underlying tool definition's `name` (snake_case)
  with kebab conversion only at the CLI surface.
