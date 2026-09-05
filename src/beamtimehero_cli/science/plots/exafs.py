"""Figures for the EXAFS pipeline (k- and R-space).

Every R-space axis label says "phase-uncorrected" — apparent distances sit
~0.3-0.5 Å below true bond lengths, and a figure must not invite the
misreading. That wording is part of the science, not decoration; keep it.

CITATIONS = {} deliberately: these are renderings of results computed in
``science/exafs/``, and carry no method of their own to attribute.
"""
from __future__ import annotations

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot_chi_extraction(energy, mu, flat, e0, k, chi, kweight, title):
    """Two-panel extraction summary: normalized mu(E) and chi(k)·k^w."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7.5))
    ax1.plot(energy, mu, color="C7", lw=1.0, alpha=0.7, label="mu (merged, /I0)")
    ax1b = ax1.twinx()
    ax1b.plot(energy, flat, color="C0", lw=1.3, label="normalized, flattened")
    ax1b.set_ylabel("normalized mu")
    ax1.axvline(e0, color="C3", lw=1.2, ls="--", label=f"E0 = {e0:.2f} eV")
    ax1.set_xlabel("Energy (eV)")
    ax1.set_ylabel("mu (arb.)")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax1b.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, fontsize=8)
    ax1.grid(alpha=0.3)
    ax1.set_title(title, fontsize=10)

    ax2.plot(k, chi * k**kweight, color="C0", lw=1.3)
    ax2.axhline(0, color="gray", ls=":", lw=1, alpha=0.7)
    ax2.set_xlabel("k (Å$^{-1}$)")
    ax2.set_ylabel(f"χ(k)·k$^{kweight}$")
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    return fig


def plot_chir(r, chir_mag, kmin, kmax, kweight, title, peak=None):
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(r, chir_mag, color="C0", lw=1.4,
            label=f"|χ(R)|, k={kmin:.1f}–{kmax:.1f} Å$^{{-1}}$, k$^{kweight}$")
    if peak and peak.get("found"):
        ax.axvline(peak["r_peak_ang"], color="C3", lw=1.1, ls="--",
                   label=f"first shell ≈ {peak['r_peak_ang']:.2f} Å (apparent)")
    ax.set_xlabel("R (Å, phase-uncorrected)")
    ax.set_ylabel(f"|χ(R)| (Å$^{{-{kweight + 1}}}$)")
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig


def plot_chi_overlay(spectra, kweight, title):
    """Overlay chi(k)·k^w for several groups. ``spectra`` = [(label, k, chi)]."""
    fig, ax = plt.subplots(figsize=(10, 6))
    for label, k, chi in spectra:
        k = np.asarray(k, dtype=float)
        ax.plot(k, np.asarray(chi, dtype=float) * k**kweight, lw=1.2, label=label)
    ax.axhline(0, color="gray", ls=":", lw=1, alpha=0.7)
    ax.set_xlabel("k (Å$^{-1}$)")
    ax.set_ylabel(f"χ(k)·k$^{kweight}$")
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig
