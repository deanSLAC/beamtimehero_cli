"""Annotated descriptor plots for interpretation outputs.

Figures are built from the arrays returned by
``descriptors.extract_descriptors`` — the plot shows exactly the numbers
the verdicts used (E0 markers, white-line fit, pre-edge fit/baseline,
per-scan trend), so a scientist can audit the interpretation at a glance.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np


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
