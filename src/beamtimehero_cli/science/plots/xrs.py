"""Figures for the XRS pipeline (energy-loss axis).

Each function returns a figure, or ``(fig, summary)`` where there is a number
worth stating in words. ``plot_elastic_fit`` takes ``file_name`` and
``scan_number``, but only to compose the title — it never reads them, so it
stays on this side of the boundary.

No CITATIONS: these render results computed in ``science/xrs/`` and carry no
method of their own to attribute.
"""
from __future__ import annotations

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot_elastic_fit(energy, signal, fit, file_name, scan_number, counter):
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(energy, signal, "o", ms=3, color="C0", label=f"{counter} (elastic scan)")
    center = fit["elastic_center_ev"]
    fwhm = fit.get("resolution_fwhm_ev")
    ax.axvline(center, color="C3", lw=1.4,
               label=f"ω=0 at {center:.3f} eV")
    if fwhm:
        ax.axvspan(center - fwhm / 2, center + fwhm / 2, color="C3", alpha=0.12,
                   label=f"FWHM = {fwhm:.3f} eV")
    ax.set_xlabel("Incident energy (eV)")
    ax.set_ylabel(f"{counter} / I0")
    ax.set_title(f"{file_name} #{scan_number} — elastic-line calibration "
                 f"({fit['method']})", fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    res = f"{fwhm:.3f} eV" if fwhm else "n/a"
    return fig, (f"Elastic line at {center:.3f} eV, resolution FWHM = {res} "
                 f"({fit['method']}).")


def plot_loss_spectrum(loss, mean, sem, title, ylabel="signal / I0"):
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(loss, mean, color="C0", lw=1.3, label="mean")
    if sem is not None and np.any(np.asarray(sem) > 0):
        ax.fill_between(loss, mean - sem, mean + sem, color="C0", alpha=0.2,
                        label="±SEM")
    ax.axvline(0, color="gray", ls=":", lw=1, alpha=0.7)
    ax.set_xlabel("Energy loss (eV)")
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig


def plot_background_subtraction(loss, raw, background, subtracted, edge_window):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7.5), sharex=True)
    ax1.plot(loss, raw, color="C0", lw=1.2, label="averaged XRS")
    ax1.plot(loss, background, color="C1", lw=1.4, ls="--", label="Compton background")
    lo, hi = edge_window
    ax1.axvspan(lo, hi, color="C2", alpha=0.10, label="edge window")
    ax1.set_ylabel("signal / I0")
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.3)
    ax2.plot(loss, subtracted, color="C3", lw=1.3, label="background-subtracted edge")
    ax2.axhline(0, color="gray", ls=":", lw=1, alpha=0.7)
    ax2.axvspan(lo, hi, color="C2", alpha=0.10)
    ax2.set_xlabel("Energy loss (eV)")
    ax2.set_ylabel("edge (bkg subtracted)")
    ax2.legend(fontsize=8)
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    return fig


def plot_overlay(spectra, ylabel="normalized signal"):
    """spectra: list of (label, loss, intensity)."""
    fig, ax = plt.subplots(figsize=(10, 6))
    for label, loss, inten in spectra:
        ax.plot(loss, inten, lw=1.3, label=label)
    ax.axvline(0, color="gray", ls=":", lw=1, alpha=0.7)
    ax.set_xlabel("Energy loss (eV)")
    ax.set_ylabel(ylabel)
    ax.set_title(f"XRS overlay — {len(spectra)} spectra", fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig


def plot_xrs_descriptors(loss, intensity, descriptors, title=""):
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(loss, intensity, color="C0", lw=1.3, label="reduced edge")
    onset = (descriptors.get("onset") or {}).get("onset_loss_ev")
    if onset is not None:
        ax.axvline(onset, color="C3", lw=1.2, ls="--", label=f"onset {onset:.1f} eV")
    wl = descriptors.get("white_line") or {}
    if wl.get("found"):
        ax.plot([wl["peak_loss_ev"]], [wl["peak_height"]], "v", color="C1", ms=9,
                label=f"white line {wl['peak_loss_ev']:.1f} eV")
    ew = (descriptors.get("windows") or {}).get("pre_edge")
    if ew:
        ax.axvspan(ew[0], ew[1], color="C2", alpha=0.10, label="pre-edge window")
    ax.axhline(0, color="gray", ls=":", lw=1, alpha=0.6)
    ax.set_xlabel("Energy loss (eV)")
    ax.set_ylabel("intensity (bkg-subtracted)")
    ax.set_title(title or "XRS descriptors", fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig


def plot_crystal_sum(loss, channels, summed, keep, labels=None):
    fig, ax = plt.subplots(figsize=(10, 6))
    labels = labels or [f"ch{i}" for i in range(len(channels))]
    for i, ch in enumerate(channels):
        kept = keep[i] if i < len(keep) else True
        ax.plot(loss, ch, lw=0.8, alpha=0.6 if kept else 0.25,
                ls="-" if kept else ":",
                label=(labels[i] + ("" if kept else " (rejected)")) if len(channels) <= 12 else None)
    ax.plot(loss, summed, color="black", lw=1.8, label="sum (kept channels)")
    ax.axvline(0, color="gray", ls=":", lw=1, alpha=0.7)
    ax.set_xlabel("Energy loss (eV)")
    ax.set_ylabel("signal")
    ax.set_title(f"Per-crystal spectra + sum ({int(sum(keep))}/{len(channels)} kept)",
                 fontsize=10)
    if len(channels) <= 12:
        ax.legend(fontsize=7, ncol=2)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig


# CITATIONS = {} deliberately: these render results computed in
# ``science/xrs/``, and carry no method of their own to attribute.
CITATIONS = {}
