# Counter selection & normalization — a load-bearing convention

**Read this before touching any multi-scan analysis tool
(`average_scans`, `analyze_convergence`, `analyze_efficiency`,
`plot_scan_stack`, `analyze_feature_evolution`, `analyze_per_spot`,
`plot_running_average`, `plot_first_half_vs_second_half`,
`plot_averaged_scans`).**

> **Module paths below are pre-`science/`.** The scientific core was gathered
> into `src/beamtimehero_cli/science/` after this was written, so read:
>
> | Written here | Now |
> |---|---|
> | `analysis.xas.pick_active_counter` | `science/reduce/counters.py` |
> | `analysis.xas.edge_step_normalize` | `science/reduce/normalize.py` |
>
> The old import paths still work as re-export shims.

These tools decide *two* things on the user's behalf that they must never
decide silently for a technique they weren't built for:

1. **which detector counter is the signal**, and
2. **how that signal is normalized** (edge-step vs. everything else).

Getting either wrong doesn't error — it returns a confident, wrong number.
This has burned a real experiment (see "The XRS incident" below). The rule:

> **The signal counter and the normalization mode are experiment inputs,
> not things the pipeline may infer from the data alone. Any tool that
> averages, compares, or scores repeated scans MUST accept an explicit
> `counter` (and, where it normalizes, an explicit normalization mode),
> and MUST report which counter and mode it actually used in its output.**

Auto-selection is a *convenience default for the XAS/HERFD/XES case*, not a
substitute for the caller stating intent.

**Status (implemented).** Every multi-scan tool now accepts an explicit
`counter` and a `normalization` mode (`edge_step` default, plus `divide_by_i0`
and `raw`), threaded through the one chokepoint
`spec_data.scans.get_normalized_scan_arrays`. When the counter is auto-picked
and looks flat next to a livelier sibling, the tools echo a `counter_warning`.
For the full X-ray Raman pipeline (elastic-line loss axis, Compton subtraction,
area normalization, q-dependence) use the dedicated `beamtimehero xrs …` branch
(`docs/xrs-analysis-branch-plan.md`) — those tools never edge-step-normalize.

---

## How auto-selection works today, and why it fails off-XAS

`analysis.xas.pick_active_counter(df)` picks the signal counter like this:

1. `ppboff` if present, else
2. among `vortDT, vortDT2, vortDT3, vortDT4`, **the one with the highest max**, else
3. `I1`.

"Highest max counts" is a fine heuristic when every candidate is a
fluorescence channel and the biggest one is the real edge. It is actively
wrong the moment a candidate channel is a **flat background / dark channel
that happens to sit at a large DC offset**.

Then `analysis.xas.edge_step_normalize(df, counter, normalize_by="I0")`
anchors the pre-edge to 0 and the post-edge to 1 using the mean of the
first/last 10 % of points. That is the correct move for an **absorption
edge step**. It is meaningless for any spectrum whose feature is **not** a
step — e.g. a bump on a sloping background — because there are no flat
pre/post plateaus to anchor to.

Every downstream verdict (`analyze_convergence`, `analyze_efficiency`,
`plot_*`) is computed on top of that normalized array. Wrong counter or
wrong normalization ⇒ every "converged / wasteful / pure noise" verdict
below it is wrong, silently.

---

## The XRS incident (why this doc exists)

X-ray Raman Spectroscopy (XRS / non-resonant inelastic scattering) measures
a **small modulation riding on a large, sloping Compton background** — the
opposite shape from an absorption edge. On a real O K-edge XRS dataset:

| channel | O-K data-scan range | what it actually is |
|---|---|---|
| `vortDT` (auto-picked) | 62590 → 66050 (~5 % modulation, huge DC offset) | **flat background / dark channel — NOT signal** |
| `vortDT2` (the macro's `plotselect`) | 171 → 466 (2.7× jump) | **the real XRS spectrum** |

Because `vortDT`'s max (66050) dwarfs `vortDT2`'s (466), `pick_active_counter`
picked `vortDT` on every scan — then edge-step-normalized a channel with no
edge. The stacks looked like "pure noise," the efficiency verdicts came back
"NaN / wasteful," and none of it was real: the pipeline was analyzing the
wrong channel with the wrong normalization. There was **no flag to override
the counter**, so the correct analysis could not be produced through the
tools at all and had to be reconstructed by hand.

Two independent bugs, both traceable to this convention being unenforced:
- **wrong counter** (auto-select can't know `vortDT2` is signal here), and
- **wrong normalization** (edge-step assumes a step; XRS has none).

---

## Where override exists today, and where it's dropped

This *has* been solved in most of the codebase. It is dropped in exactly the
layer that matters most — the automated multi-scan aggregators the chat
agents lean on.

| surface | counter override? | notes |
|---|---|---|
| `plot_scan` (single scan) | ✅ `counter`, `normalize_by` | |
| `normalize_scan` (single scan) | ✅ `counter`, `normalize_by` | |
| chemcatal notebook `bl_data_analysis.average/normalize/plot` | ✅ `signal=`, `reference=` | |
| chemcatal `skills/registry` | ✅ `signal` field | |
| portal viewer / beamtimes API | ✅ `signal=` query param | |
| **`average_scans`** | ❌ none | funnels through `get_normalized_scan_arrays` |
| **`analyze_convergence`** | ❌ none | same |
| **`analyze_efficiency`** | ❌ none | same (+ Poisson floor read off the auto counter) |
| **`plot_scan_stack`** | ❌ none | same |
| **`analyze_feature_evolution`** | ❌ none | same |
| **`analyze_per_spot`** | ❌ none | same |
| **`plot_running_average` / `plot_first_half_vs_second_half`** | ❌ none | same |
| **`plot_averaged_scans`** | ❌ none | same |

Root cause: **one chokepoint.** `spec_data.scans.get_normalized_scan_arrays()`
hardcodes `get_active_counter(...)` → `edge_step_normalize(...)`. Every
multi-scan tool sits on top of it, so none of them can express "use this
counter" or "don't edge-step-normalize" no matter what the tool schema says.

---

## The contract for new / fixed tools

1. **Every multi-scan tool takes an optional `counter`.** When omitted it may
   fall back to `pick_active_counter`, but the fallback's chosen counter
   **and reason** must appear in the returned payload so the agent can catch
   a bad pick.
2. **`get_normalized_scan_arrays` threads `counter` through** instead of
   calling `get_active_counter` internally. That is the single change that
   unlocks override for all nine tools at once.
3. **Normalization is selectable, not assumed.** Add a normalization mode
   (`edge_step` default, plus at least a `raw`/`divide_by_i0` and an
   XRS-appropriate `area` / background-subtracted mode). Edge-step must never
   be silently applied to a non-edge technique.
4. **Guardrail:** when the auto-picked counter is a suspiciously flat,
   high-offset channel (low fractional modulation, large DC offset) relative
   to a lower-max sibling, the tool should *warn* rather than proceed
   silently — that is the exact `vortDT` vs `vortDT2` signature.
5. **Prefer the macro's `plotselect` counter as the auto default** when it is
   recorded for the scan: the person who wrote the scan macro already told us
   which channel is signal (`plotselect vortDT2`). Trust that over "highest max."

If you add a technique branch (e.g. XRS), it does **not** get to reuse
`edge_step_normalize`. It brings its own normalization and its own counter
default, and it still honors an explicit `counter`.
