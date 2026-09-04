"""XRS interpretation engine: descriptors → structured chemical verdicts.

Mirrors the XAS ``interpretation.interpret`` output contract:

    {estimate, range, confidence, basis, descriptors_used, calibration_context,
     flags, provenance, caveats, narration}

with ``confidence`` in {high, medium, low, refused}. Narration is assembled from
the computed numbers, never invented. Rigor gates are honest: absolute edge
positions need an elastic-line calibration and an energy reference; intensity
verdicts are relative unless area/absolute-normalized.

The interpretation moves are the XANES-transferable ones, on the loss axis:
edge-onset shift → oxidation-state proxy; O-K pre-edge intensity → TM 3d–O 2p
covalency / oxygen redox; C-K π*/σ* weight → sp²/sp³ + functional groups;
metal L3/L2 branching → oxidation state; feature vs q → dipole (low q) vs
monopole/quadrupole (high q).
"""
from __future__ import annotations

import numpy as np


def _verdict(basis, descriptors_used, flags, provenance) -> dict:
    return {
        "estimate": None,
        "range": None,
        "confidence": "refused",
        "basis": basis,
        "descriptors_used": descriptors_used,
        "calibration_context": None,
        "flags": list(flags),
        "provenance": provenance,
        "caveats": [],
        "narration": "",
    }


# ---------------------------------------------------------------------------
# Oxidation state / covalency
# ---------------------------------------------------------------------------

def interpret_xrs_oxidation_state(descriptors: dict, calibration: dict | None = None) -> dict:
    """Oxidation-state / covalency read from a reduced XRS edge.

    - Absolute edge-onset position (→ oxidation state via reference couples)
      requires an elastic-line calibration AND an assigned reference; without
      both, the absolute call is refused and only relative content is reported.
    - For an O K-edge: the pre-edge fraction is reported as a TM 3d–O 2p
      covalency / oxygen-redox indicator (a growing low-loss pre-edge on charge
      is the anion-redox signature).
    """
    edge = descriptors.get("edge") or {}
    family = edge.get("family", "other")
    onset = (descriptors.get("onset") or {}).get("onset_loss_ev")
    pre_frac = descriptors.get("pre_edge_fraction")
    wl = descriptors.get("white_line") or {}
    flags = list(descriptors.get("flags", []))

    v = _verdict(
        basis="xrs_edge_onset_and_preedge",
        descriptors_used={
            "onset_loss_ev": onset,
            "pre_edge_fraction": pre_frac,
            "white_line_loss_ev": wl.get("peak_loss_ev"),
        },
        flags=flags,
        provenance={
            "axis": "energy_loss_ev",
            "note": ("XRS near-edge in the low-q dipole limit reproduces dipole "
                     "XANES (Mizuno-Ohmura); onset/pre-edge interpretation is "
                     "transferable, with q as an extra probe."),
        },
    )
    calibrated = bool(calibration and calibration.get("calibrated"))
    v["calibration_context"] = calibration or {"calibrated": False}

    parts = []
    if onset is not None:
        parts.append(f"edge onset at {onset:.1f} eV loss")
    if calibrated and onset is not None and calibration.get("assigned_reference_ev") is not None:
        shift = onset + float(calibration.get("offset_ev", 0.0)) - float(calibration["assigned_reference_ev"])
        v["estimate"] = f"onset {shift:+.1f} eV vs {calibration.get('reference_source', 'reference')}"
        v["confidence"] = "medium"
        v["narration"] = (
            f"Calibrated edge onset shift {shift:+.1f} eV relative to the reference "
            f"— positive ⇒ higher oxidation state (larger core binding energy)."
        )
    else:
        v["confidence"] = "low"
        v["flags"].append("refused_absolute_no_calibration")
        v["caveats"].append(
            "No elastic-line + reference calibration: absolute oxidation state "
            "refused; reporting shape/relative content only. Run "
            "calibrate_energy_loss and record a reference."
        )
        v["narration"] = "Relative read only (uncalibrated loss axis). "

    if family == "low_Z_K" and edge.get("element") == "O" and pre_frac is not None:
        v["narration"] += (
            f" O K-edge pre-edge fraction = {pre_frac:.2f}: the O 1s→(TM 3d–O 2p) "
            f"pre-edge tracks TM–O covalency; a low-loss pre-edge that GROWS on "
            f"charge is the oxygen-redox (O 2p hole) signature in cathodes."
        )
        v["basis"] = "o_k_preedge_covalency"
    elif family == "3d_L":
        v["narration"] += (
            " 3d metal L-edge: oxidation state is best read from the L3/L2 "
            "branching ratio — provide both L3 and L2 windows (interpret_q_dependence "
            "or two peak windows) for a quantitative call."
        )
        v["caveats"].append("Branching-ratio oxidation state needs both L3 and L2 peaks.")
    elif family == "low_Z_K" and edge.get("element") == "C":
        v["narration"] += (
            " C K-edge: π* (~285 eV) vs σ* (~292 eV) spectral-weight tracks sp²/sp³; "
            "carbonyl/carbonate π* (~286.5–290 eV) fingerprint functional groups."
        )
    return v


# ---------------------------------------------------------------------------
# q-dependence: dipole (low q) vs monopole/quadrupole (high q)
# ---------------------------------------------------------------------------

def interpret_q_dependence(feature_by_q: list[dict]) -> dict:
    """Classify a feature's momentum-transfer behavior.

    ``feature_by_q`` = list of ``{"q": Å⁻¹, "value": <area-normalized feature
    intensity/area>}`` (≥3 points). A feature whose area-normalized intensity
    RISES with q beyond noise has non-dipole (monopole/quadrupole) character; a
    flat trend is dipole-like (XANES-transferable). Returns the verdict contract.
    """
    pts = [(float(d["q"]), float(d["value"])) for d in feature_by_q
           if d.get("q") is not None and d.get("value") is not None]
    v = _verdict(
        basis="feature_intensity_vs_q",
        descriptors_used={"n_points": len(pts), "points": pts},
        flags=[],
        provenance={"note": ("Low q ≈ dipole (s→p, XANES-like); rising with q ⇒ "
                             "monopole/quadrupole turn-on (Sahle 2015; Mizuno-Ohmura).")},
    )
    if len(pts) < 3:
        v["caveats"].append("Need ≥3 q points to classify q-dependence.")
        return v
    q = np.array([p[0] for p in pts]); val = np.array([p[1] for p in pts])
    # Pearson correlation of normalized feature vs q, plus fractional change.
    if np.std(q) == 0 or np.std(val) == 0:
        v["caveats"].append("Degenerate q or value spread.")
        return v
    r = float(np.corrcoef(q, val)[0, 1])
    frac_change = float((val[np.argmax(q)] - val[np.argmin(q)]) / (abs(np.mean(val)) + 1e-30))
    v["descriptors_used"].update({"pearson_r_value_vs_q": round(r, 3),
                                  "fractional_change_low_to_high_q": round(frac_change, 3)})
    if r > 0.6 and frac_change > 0.2:
        v["estimate"] = "non-dipole (monopole/quadrupole) character"
        v["confidence"] = "medium"
        v["narration"] = (
            f"Feature intensity rises with q (r={r:.2f}, +{frac_change*100:.0f}% "
            f"low→high q): monopole/quadrupole (s→s / s→d) character growing at high "
            f"q — a non-dipole transition, dipole-forbidden or weak in XANES.")
    elif abs(r) <= 0.6 or abs(frac_change) <= 0.2:
        v["estimate"] = "dipole-like (q-independent shape)"
        v["confidence"] = "medium"
        v["narration"] = (
            f"Feature is ~q-independent (r={r:.2f}, {frac_change*100:+.0f}%): dipole "
            f"character — the low-q spectrum is comparable to dipole XANES.")
    else:
        v["estimate"] = "decreasing with q"
        v["confidence"] = "low"
        v["narration"] = f"Feature weakens with q (r={r:.2f})."
    return v


# ---------------------------------------------------------------------------
# Reference comparison (linear-combination fit)
# ---------------------------------------------------------------------------

def compare_xrs_to_references(loss, intensity, references: list[dict]) -> dict:
    """Non-negative linear-combination fit of a spectrum to reference spectra.

    ``references`` = list of ``{"name", "loss", "intensity"}``. All are
    interpolated onto the target loss grid, then fit with non-negative least
    squares; fractions are normalized to sum 1. Valid against XANES references
    in the LOW-q dipole regime. Returns fractions + fit residual.

    The fit itself is axis-agnostic and lives in ``generic_data.lcf``
    (promoted from here); this wrapper keeps the XRS-facing name, the
    ``loss`` reference key, and the dipole-regime caveat.
    """
    from beamtimehero_cli.science.xas.compare import compare_to_references

    out = compare_to_references(loss, intensity, references)
    if "error" not in out:
        out["regime_caveat"] = (
            "LCF against XANES references is valid in the low-q dipole "
            "limit; at high q multipole intensity breaks the equivalence."
        )
    return out


# ---------------------------------------------------------------------------
# Quality + capstone summary
# ---------------------------------------------------------------------------

def assess_xrs_quality(descriptors: dict, resolution_fwhm_ev: float | None = None) -> dict:
    """Quality gate for a reduced XRS edge: feature SNR, resolution, flags."""
    snr = (descriptors.get("feature_snr") or {}).get("snr")
    flags = list(descriptors.get("flags", []))
    if snr is None:
        verdict = "unknown"
    elif snr >= 10:
        verdict = "publication"
    elif snr >= 5:
        verdict = "usable"
    elif snr >= 3:
        verdict = "marginal"
    else:
        verdict = "noise_limited"
    out = {
        "feature_snr": snr,
        "resolution_fwhm_ev": resolution_fwhm_ev,
        "verdict": verdict,
        "flags": flags,
        "note": ("SNR is measured on the edge feature above the post-edge, NOT the "
                 "whole spectrum (which the Compton background dominates)."),
    }
    if resolution_fwhm_ev is None:
        out.setdefault("caveats", []).append(
            "No elastic FWHM — run calibrate_energy_loss to report energy resolution.")
    return out


def summarize_xrs_chemistry(descriptors: dict, calibration: dict | None = None,
                            resolution_fwhm_ev: float | None = None) -> dict:
    """Capstone: oxidation/covalency verdict + quality + one narration paragraph."""
    ox = interpret_xrs_oxidation_state(descriptors, calibration)
    quality = assess_xrs_quality(descriptors, resolution_fwhm_ev)
    edge = descriptors.get("edge") or {}
    onset = (descriptors.get("onset") or {}).get("onset_loss_ev")
    wl = descriptors.get("white_line") or {}
    narration = (
        f"{edge.get('element', '?')} {edge.get('edge', '')} XRS edge "
        f"(onset ≈ {onset:.1f} eV loss" + (f", white line {wl['peak_loss_ev']:.1f} eV" if wl.get('peak_loss_ev') else "")
        + f"). Feature SNR {quality['feature_snr']} → quality '{quality['verdict']}'. "
        + ox["narration"]
    ) if onset is not None else ox["narration"]
    return {
        "oxidation_state": ox,
        "quality": quality,
        "narration": narration,
        "descriptors": descriptors,
    }
