"""The scientific and mathematical core of the beamtimehero toolbelt.

**The rule for everything in this package:** it takes *numbers in* and returns
*numbers out*. No file paths, no environment variables, no SPEC, no application
database, no argparse.

The one sanctioned exception is ``xraydb``, whose tabulated edge energies and
emission lines come from a read-only table bundled with the library. It is a
constant lookup, not I/O the caller has to arrange — treat it like a physical
constant. Everything else stays pure.

Corollaries, which double as a routing rule:

* Needs to know *where the data lives*  -> ``beamtimehero_cli.spec_data``
* Needs to know *what the agent asked for* -> ``beamtimehero_cli.tool_catalog``
* Takes arrays and returns a dict of numbers -> it belongs here.

Organized by technique, then pipeline stage:

    tables/    tabulated physics (edge energies, shifts, emission lines)
    reduce/    detector counts -> one clean spectrum (technique-agnostic)
    xas/       XANES / HERFD
    exafs/     k-space: chi(k), background, Fourier transform
    xrs/       X-ray Raman on the energy-loss axis
    fitting/   generic curve fits for beam diagnostics and alignment
    plots/     figures over arrays and descriptor dicts

See ``README.md`` in this directory for the full map and the
"you want to change X -> go to Y" table.
"""
