# `science/` — the scientific and mathematical core

This is where the physics lives. If you are a scientist contributing to this
project, **this directory is your working area**, and you should not need to
read the toolbelt machinery to work in it.

## The one rule

> Everything under `science/` takes **numbers in** and returns **numbers out**.
> No file paths, no environment variables, no SPEC, no database, no argparse.

You can check this from a function's signature alone, which is the point. The
corollaries double as a routing rule:

| If your function… | …it belongs in |
|---|---|
| needs to know *where the data lives* | `beamtimehero_cli/spec_data/` |
| needs to know *what the agent asked for* | `beamtimehero_cli/tool_catalog/` |
| takes arrays and returns a dict of numbers | **here** |

For plotting specifically: a figure function that takes **arrays or a descriptor
dict** goes in `science/plots/`; one that takes a **file name** goes in
`spec_data/`.

## The layout

Organized by **technique, then pipeline stage** — the order you'd look something
up in, not the order the code was written.

```
science/
├── tables/     tabulated physics. data, not algorithms.
│   ├── edges.py            edge energies, families, edge suggestion
│   ├── edge_shifts.py      per-element eV/valence slopes, core-hole widths
│   ├── emission_lines.py   preferred Siegbahn line per edge
│   └── xrs_edges.py        XRS edge assignments
├── reduce/     detector counts → one clean spectrum. technique-agnostic.
│   ├── counters.py         which channel carries the signal (+ flat-channel warning)
│   ├── normalize.py        per-scan monitor / edge-step normalization
│   ├── reps.py             averaging and filtering across repeated scans
│   ├── deadtime.py         ICR-based non-paralyzable correction
│   └── artifacts.py        glitch, saturation, self-absorption flags
├── xas/        XANES / HERFD
│   ├── normalize.py        area (Bugarin & Glatzel), MBACK, Athena-style pre/post
│   ├── e0.py               edge position, core-hole re-broadening
│   ├── fits.py             pseudo-Voigt pre-edge and white-line fits
│   ├── descriptors.py      the descriptor bundle the interpret_* tools consume
│   ├── compare.py          E0 registration, difference spectra, LCF
│   ├── interpret.py        oxidation state, coordination geometry, summary
│   └── policy.py           ★ the defaults and heuristics
├── exafs/      k-space
│   ├── kspace.py           E ↔ k, k-grid rebinning
│   ├── background.py       AUTOBK-lite spline removal
│   ├── fourier.py          windowed FT into R space, first-shell peak
│   └── policy.py           ★ k-weight, k range, window taper, R_bkg
├── xrs/        X-ray Raman, energy-loss axis
│   ├── calibrate.py        elastic line → loss axis, momentum transfer
│   ├── reduce.py           crystal summing, Compton background, area norm
│   ├── descriptors.py
│   └── interpret.py
├── fitting/    generic curve fits — beam diagnostics and alignment, NOT spectra
│   └── similarity.py
└── plots/      figures over arrays / descriptor dicts
    ├── xas.py              annotated descriptor figure
    └── scan.py             generic scan render
```

## You want to change… → go to

| You want to change… | Go to |
|---|---|
| an edge energy, core-hole width, or edge-shift slope | `tables/` |
| which counter is picked, or how reps are averaged | `reduce/` |
| how μ(E) is normalized (area, edge-step, MBACK) | `xas/normalize.py` |
| how E₀ is found, or core-hole re-broadening | `xas/e0.py` |
| the pre-edge or white-line fit itself | `xas/fits.py` |
| what goes into the descriptor bundle | `xas/descriptors.py` |
| how an oxidation state or geometry verdict is reached | `xas/interpret.py` |
| a default window, k-weight, component count, or auto-detection rule | `<technique>/policy.py` |
| χ(k) extraction, background, or the Fourier transform | `exafs/` |
| the energy-loss axis, Compton background, or crystal summing | `xrs/` |
| a knife-edge / aperture / emission-peak fit for alignment | `fitting/` |
| what a plot looks like | `plots/` |

## `policy.py` — where the defaults live

Each technique has a `policy.py` holding the scientific *choices* as distinct
from the computations: fit windows, how many white-line components an edge
family needs, how the absorber is guessed when the caller doesn't say, the
default k-weight, the minimum data a fit needs.

These used to sit inline in the tool handlers, several of them duplicated
across handlers (the default k-weight appeared five times). They are collected
here so changing a default is a one-line edit in an obvious file — and so each
choice can carry the citation that justifies it.

**If you are changing a number, it probably belongs in a `policy.py`.**

## Conventions

**Citations.** Every module that implements a published method names its
source, either in the function docstring or as a module-level constant
(`AREA_NORM_CITATION`, `EDGE_ENERGY_SOURCE`, `CORE_HOLE_WIDTH_SOURCE`). If you
add a method, add the reference — this directory should read like a methods
section.

**Provenance.** Anything that produces a number a scientist might quote also
reports how it was produced: which normalization, which fit window, which
baseline model, which calibration. See `xas/descriptors.py` for the pattern.

**Degrade, don't crash.** A fit that fails should return a flag and an
unchanged spectrum, not raise. Tools call these functions inside an agent loop;
an exception becomes an opaque failure, a flag becomes something the agent can
report and work around.

## Moved from

The old locations are re-export shims, so existing imports keep working:

| Old | New |
|---|---|
| `analysis/xas.py` | `science/reduce/{counters,normalize,reps,deadtime}.py`, `science/xas/compare.py` |
| `analysis/exafs.py` | `science/exafs/{kspace,background,fourier}.py` |
| `analysis/xrs.py` | `science/xrs/{calibrate,reduce}.py` |
| `analysis/render.py` | `science/plots/scan.py` |
| `interpretation/descriptors.py` | `science/xas/{e0,fits,descriptors}.py` |
| `interpretation/normalize.py` | `science/xas/normalize.py`, `science/tables/emission_lines.py` |
| `interpretation/{edges,calibrations,xrs_edges}.py` | `science/tables/` |
| `interpretation/quality.py` | `science/reduce/artifacts.py` |
| `interpretation/interpret.py` | `science/xas/interpret.py` |
| `interpretation/xrs_*.py` | `science/xrs/` |
| `interpretation/plotting.py` | `science/plots/xas.py` |
| `interpretation/calibration_store.py` | `beamtimehero_cli/calibration_store.py` (session state, not science) |
| `generic_data/lcf.py` | `science/xas/compare.py` |
| `generic_data/cosine_similarity.py` | `science/fitting/similarity.py` |

New code should use the new paths. The shims will be removed once the
consuming applications have migrated.
