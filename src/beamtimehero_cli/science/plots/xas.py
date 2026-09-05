"""Annotated descriptor plots for interpretation outputs.

Figures are built from the arrays returned by
``descriptors.extract_descriptors`` — the plot shows exactly the numbers
the verdicts used (E0 markers, white-line fit, pre-edge fit/baseline,
per-scan trend), so a scientist can audit the interpretation at a glance.
"""
from __future__ import annotations

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def annotated_descriptor_figure(descriptors: dict, arrays: dict, title: str = ""):
    """One figure: spectrum + fits, pre-edge zoom, optional trend panel."""
    trends = descriptors.get("per_scan_trends")
    n_rows = 2 if trends else 1
    fig, axes = plt.subplots(
        n_rows, 2, figsize=(11, 4.2 * n_rows), squeeze=False,
        gridspec_kw={"width_ratios": [1.6, 1.0]},
    )
    ax_main, ax_pre = axes[0]

    energy, mu = arrays["energy"], arrays["mu"]
    e0 = descriptors["e0"]["e0_ev"]
    ax_main.plot(energy, mu, lw=1.0, color="#1f77b4", label="normalized μ(E)")
    glitch = arrays.get("glitch_mask")
    if glitch is not None and glitch.any():
        ax_main.plot(energy[glitch], mu[glitch], "x", color="red", ms=5,
                     label=f"glitch-masked ({int(glitch.sum())})")
    ax_main.axvline(e0, color="k", ls="--", lw=0.8,
                    label=f"E0 = {e0:.2f} eV (deriv-max)")
    half = descriptors["e0"].get("e0_half_step_ev")
    if half is not None:
        ax_main.axvline(half, color="gray", ls=":", lw=0.8,
                        label=f"E0 = {half:.2f} eV (half-step)")

    wl_arr = arrays.get("white_line")
    wl = descriptors.get("white_line") or {}
    if wl_arr is not None and wl.get("fit_ok"):
        ax_main.plot(wl_arr["e"], wl_arr["fit"], color="#d62728", lw=1.2,
                     label="white-line fit")
        wle = wl.get("white_line_energy_ev")
        if wle is not None:
            ax_main.axvline(wle, color="#d62728", ls=":", lw=0.8)
    norm_method = descriptors["provenance"]["normalization"].get("method")
    ax_main.set_xlabel("Energy (eV)")
    ax_main.set_ylabel(f"μ(E) ({norm_method}-normalized)")
    ax_main.legend(fontsize=7, loc="lower right")
    ax_main.set_title(title or "XANES descriptors")

    pe_arr = arrays.get("pre_edge")
    pe = descriptors.get("pre_edge") or {}
    if pe_arr is not None and pe.get("fit_ok"):
        ax_pre.plot(pe_arr["e"], pe_arr["y"], ".", ms=3, color="#1f77b4",
                    label="data")
        ax_pre.plot(pe_arr["e"], pe_arr["fit"], color="#d62728", lw=1.2,
                    label="fit")
        ax_pre.plot(pe_arr["e"], pe_arr["baseline"], color="gray", ls="--",
                    lw=0.9, label="baseline")
        if pe.get("centroid_ev") is not None:
            ax_pre.axvline(pe["centroid_ev"], color="k", ls=":",
                           label=f"centroid {pe['centroid_ev']:.2f} eV")
        ax_pre.set_title(
            f"Pre-edge fit ({pe['n_components']} comp., "
            f"R={pe['r_factor']:.2e})", fontsize=9,
        )
        ax_pre.legend(fontsize=7)
    else:
        ax_pre.text(0.5, 0.5, "no usable pre-edge fit",
                    ha="center", va="center", transform=ax_pre.transAxes)
    ax_pre.set_xlabel("Energy (eV)")

    if trends:
        ax_t1, ax_t2 = axes[1]
        per = trends["per_metric"]
        e0_t = per.get("e0_ev")
        if e0_t:
            vals = np.array(e0_t["values"])
            x = np.arange(1, len(vals) + 1)
            drift = e0_t.get("monotonic_drift")
            ax_t1.plot(x, vals - vals[0], "o-", ms=3,
                       color="#d62728" if drift else "#2ca02c")
            ax_t1.axhline(0, color="gray", lw=0.5)
            ax_t1.set_xlabel("scan #")
            ax_t1.set_ylabel("ΔE0 (eV)")
            ax_t1.set_title(
                "E0 per scan — " + ("MONOTONIC DRIFT" if drift else "stable"),
                fontsize=9,
            )
        for name, style in (("white_line_height", "-o"),
                            ("pre_edge_intensity", "-s")):
            t = per.get(name)
            if not t or "values" not in t:
                continue
            vals = np.array(t["values"])
            ref = vals[0] if vals[0] != 0 else 1.0
            ax_t2.plot(np.arange(1, len(vals) + 1), 100 * (vals / ref - 1),
                       style, ms=3, label=name.replace("_", " "))
        ax_t2.axhline(0, color="gray", lw=0.5)
        ax_t2.set_xlabel("scan #")
        ax_t2.set_ylabel("change vs first scan (%)")
        ax_t2.set_title("intensity metrics per scan", fontsize=9)
        ax_t2.legend(fontsize=7)

    fig.tight_layout()
    return fig


def plot_alignment_overlay(records, labels):
    """Two-panel before/after overlay for ``science.xas.compare.align_spectra`` output.

    ``records`` are the per-spectrum dicts align_spectra returns (shifted
    energies + shift bookkeeping); ``labels`` is a parallel name list.
    Returns ``(fig, summary)``.
    """
    fig, (ax_before, ax_after) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    for rec, label in zip(records, labels):
        energy_before = rec["energy"] - rec["shift_applied"]
        ax_before.plot(energy_before, rec["mu"], linewidth=1.2, label=label)
        if rec.get("refused"):
            suffix = " (shift refused)"
        else:
            suffix = f" ({rec['shift_applied']:+.2f} eV)"
        ax_after.plot(rec["energy"], rec["mu"], linewidth=1.2, label=label + suffix)

    target = records[0].get("target_e0") if records else None
    ax_before.set_title("Before alignment (as recorded)", fontsize=10)
    ax_after.set_title(
        f"After E0 alignment (target E0 = {target:.2f} eV)" if target is not None
        else "After E0 alignment", fontsize=10)
    for ax in (ax_before, ax_after):
        ax.set_ylabel("normalized signal")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    ax_after.set_xlabel("Energy (eV)")
    fig.tight_layout()

    shifts = ", ".join(
        "{}: {}".format(
            lbl,
            "refused" if r.get("refused") else f"{r['shift_applied']:+.2f} eV",
        )
        for r, lbl in zip(records, labels)
    )
    return fig, f"E0 alignment overlay ({len(records)} spectra). Shifts: {shifts}."


def plot_difference_spectrum(result, label_a="A", label_b="B"):
    """Two-panel view of ``science.xas.compare.difference_spectrum`` output:
    overlaid A and B on the common grid, then A − B. Returns ``(fig, summary)``.
    """
    energy = result["energy"]
    stats = result["stats"]

    fig, (ax_top, ax_diff) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    ax_top.plot(energy, result["a"], linewidth=1.2, label=label_a, color="C0")
    ax_top.plot(energy, result["b"], linewidth=1.2, label=label_b, color="C3")
    ax_top.set_ylabel("normalized signal")
    ax_top.set_title(
        f"{label_a} vs {label_b}"
        + (" (E0-aligned)" if result.get("aligned") else " (raw energy axes)"),
        fontsize=10)
    ax_top.legend(fontsize=8)
    ax_top.grid(alpha=0.3)

    ax_diff.plot(energy, result["difference"], linewidth=1.2, color="C2",
                 label=f"{label_a} − {label_b}")
    ax_diff.axhline(0.0, color="gray", linewidth=0.8, alpha=0.7)
    ax_diff.axvline(stats["energy_of_max_abs_delta_ev"], color="C1",
                    linestyle="--", alpha=0.6,
                    label=f"max |Δ| = {stats['max_abs_delta']:.4g} "
                          f"@ {stats['energy_of_max_abs_delta_ev']:.1f} eV")
    ax_diff.set_xlabel("Energy (eV)")
    ax_diff.set_ylabel("Δ signal")
    ax_diff.legend(fontsize=8)
    ax_diff.grid(alpha=0.3)
    fig.tight_layout()

    return fig, (
        f"Difference {label_a} − {label_b}: max |Δ| = {stats['max_abs_delta']:.4g} "
        f"at {stats['energy_of_max_abs_delta_ev']:.1f} eV, "
        f"rms Δ = {stats['rms_delta']:.4g} over {stats['n_points']} points."
    )


def plot_lcf_fit(energy, target, fit, residual, components, title=""):
    """Two-panel XANES LCF view: target + best fit, then the residual.

    ``components`` = the fraction dicts ``science.xas.compare.compare_to_references`` returns
    (``{name, fraction, ...}``), rendered into the fit legend entry.
    Returns ``(fig, summary)``.
    """
    frac_text = " + ".join(
        f"{c['fraction']:.2f}·{c['name']}" for c in components
    )

    fig, (ax_fit, ax_res) = plt.subplots(
        2, 1, figsize=(10, 8), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]})
    ax_fit.plot(energy, target, linewidth=1.4, color="C0", label="target")
    ax_fit.plot(energy, fit, linewidth=1.2, color="C3", linestyle="--",
                label=f"LCF fit: {frac_text}")
    ax_fit.set_ylabel("normalized signal")
    if title:
        ax_fit.set_title(title, fontsize=10)
    ax_fit.legend(fontsize=8)
    ax_fit.grid(alpha=0.3)

    ax_res.plot(energy, residual, linewidth=1.0, color="C2", label="residual")
    ax_res.axhline(0.0, color="gray", linewidth=0.8, alpha=0.7)
    ax_res.set_xlabel("Energy (eV)")
    ax_res.set_ylabel("residual")
    ax_res.legend(fontsize=8)
    ax_res.grid(alpha=0.3)
    fig.tight_layout()

    return fig, f"LCF fit: {frac_text}."


# ---------------------------------------------------------------------------
# CITATIONS — method -> reference. ``None`` means the method is implemented
# but not yet attributed; those surface as gaps on the generated science
# index, and filling one in is a welcome contribution. See science/README.md.
# ---------------------------------------------------------------------------

# CITATIONS = {} deliberately: these render results computed in
# ``science/xas/``, and carry no method of their own to attribute.
CITATIONS = {}
