# XRS (X-ray Raman) analysis — the dedicated `xrs` branch

**Read this before analyzing X-ray Raman scattering (XRS / NRIXS) data.**
XRS has its own tool branch (`beamtimehero xrs …`; chat-agent profiles
surface the same leaves, e.g. `cc average-xrs-scans`). The XAS/HERFD/XES
tools are wrong for XRS **by construction** — not merely suboptimal.

## What XRS measures

Hard X-rays (~10 keV) go in and out; the analyzer sits at a fixed energy Ω
and the monochromator Ω₀ is scanned. The abscissa is **energy loss
ω = Ω₀ − Ω** and the measured quantity is the dynamic structure factor
**S(q,ω)** — not an absorption coefficient. It gives soft-X-ray-like edge
information (C, N, O, Li K-edges...) with hard-X-ray penetration, so it works
through in-situ cells and battery casings. The momentum transfer **q** (set by
the scattering angle 2θ) is an extra physics knob: low q ≈ dipole-limit
(XAS-like) spectra, high q brings in multipole transitions.

## Why the XAS tools fail on XRS data

| | XAS / HERFD / XES | XRS / NRIXS |
|---|---|---|
| x-axis | incident/emission energy | **energy loss**, referenced to the elastic line |
| feature shape | edge step (+ EXAFS) | **weak bump on a large sloping Compton background** — no step |
| normalization | edge-step (pre→0, post→1) | **area** (or f-sum) — edge-step is meaningless |
| rep alignment | `find_e0` (max derivative) | **elastic line** (max derivative sits on the Compton rise) |
| signal counter | brightest fluorescence channel | the channel showing the **elastic line + edge**, not the brightest |

Concretely: the multi-scan XAS tools' auto-picked counter can select a flat
dark channel with a large DC offset (the `vortDT`-over-`vortDT2` trap), and
edge-step normalization anchors to plateaus that do not exist in an XRS
spectrum. Every downstream convergence/efficiency verdict is then silently
wrong. If you must run an XAS multi-scan tool on XRS scans, pass an explicit
`counter` and `normalization` (see `beamtimehero ref counter-selection`) —
but prefer the `xrs` branch.

## The reduction pipeline (run in this order)

1. `calibrate_energy_loss` — fit the elastic (Rayleigh) line from an elastic
   scan (`ascan mono`): center → ω = 0, FWHM → energy resolution. Persists the
   calibration when the data mount is writable; on a read-only mount it still
   returns the center (persistence is best-effort).
2. `build_loss_axis` — convert a scan's mono axis to energy loss using the
   elastic calibration.
3. `average_xrs_scans` — average reps **aligned on the elastic line** with an
   explicit signal counter; never `find_e0`.
4. `subtract_compton_background` — remove the sloping Compton/valence
   background under the feature.
5. `normalize_xrs` — area normalization over the feature window (never
   edge-step).

Multi-crystal / multi-ROI data: `sum_crystals`, `align_crystals` (per-crystal
elastic alignment before summing), `tag_crystal_q` (record each channel's q so
q-dependence is analyzable). Overlay processed spectra with
`overlay_xrs_spectra`.

## Interpretation

- `summarize_xrs_chemistry` — the capstone verdict on a processed spectrum.
- `interpret_xrs_oxidation_state` — oxidation-state reading from edge-onset /
  feature shifts on the loss axis (subject to the elastic calibration; report
  the confidence and caveats the tool returns).
- `interpret_q_dependence` — dipole-vs-multipole content across q.
- `compare_xrs_to_references` — fingerprinting against reference spectra.
- `assess_xrs_quality` — rep agreement / statistics verdict (use this instead
  of the edge-step convergence tools).
- `extract_xrs_descriptors` — the raw numeric descriptors behind the verdicts.

Report XRS findings on the **energy-loss axis** (feature position/shape,
q-dependence) — never as an absorption-edge position or an
edge-step-derived valence.

## Open items to confirm with the beamline

The defaults encode the cathode-campaign data layout (Vortex SDD, few ROIs,
signal on `vortDT2`, elastic scans as `ascan mono`). Confirm before leaning
on them: exact SPEC macro names, the `vortDT`/`vortDT2` channel semantics,
the spectrometer configuration in use, and per-channel q values. Design
history and Phase-3 extensions (f-sum/absolute normalization, simulation
comparison, NeXus export): `docs/xrs-analysis-branch-plan.md`.
