"""Hybrid interpretation engine: descriptors -> structured chemical verdicts.

Every verdict follows one output contract:

    {estimate, range, confidence, basis, descriptors_used,
     calibration_context, flags, provenance, caveats, narration}

with ``confidence`` in {high, medium, low, refused}. The narration is
assembled from the computed numbers — never invented. The rigor gates:

- Absolute oxidation states from POSITIONS (edge, centroid, peak) are read
  on the session energy axis. Per instrument spec the monochromator is
  foil-calibrated at beamtime start and its step-loss drift is
  ``absev``-compensated, so in the absence of an explicit calibration
  record the axis is ASSUMED foil-calibrated (edges at their tabulated
  positions, ~0.2 eV systematic; see
  ``calibration_store.current_calibration``). An explicit recorded
  calibration takes precedence and tightens the anchor.
- Conventional-domain calibrations (Wilke 2001) are only applied to the
  re-broadened spectrum; using the sharp HERFD fit instead is flagged
  ``calibration_domain_mismatch`` and capped at low confidence.
- Intensity-based verdicts are degraded while ``self_absorption_risk``
  stands (fluorescence-detected HERFD, unknown concentration).
"""
from __future__ import annotations

import numpy as np

from beamtimehero_cli.interpretation import calibrations as cal


def _verdict(basis: str, descriptors_used: dict, calibration_context: dict,
             flags: list[str], provenance: dict) -> dict:
    return {
        "estimate": None,
        "range": None,
        "confidence": "refused",
        "basis": basis,
        "descriptors_used": descriptors_used,
        "calibration_context": calibration_context,
        "flags": list(flags),
        "provenance": provenance,
        "caveats": [],
        "narration": "",
    }


def _degrade(confidence: str, to: str = "low") -> str:
    order = ["refused", "low", "medium", "high"]
    return order[min(order.index(confidence), order.index(to))]


# ---------------------------------------------------------------------------
# Oxidation state
# ---------------------------------------------------------------------------

def interpret_oxidation_state(descriptors: dict, calibration: dict) -> dict:
    edge_info = descriptors.get("edge") or {}
    family = edge_info.get("family", "other")
    element = edge_info.get("element")
    flags = list(descriptors.get("flags", []))

    handler = {
        "3d_K": _oxidation_3d_k,
        "4d_K": _oxidation_4d_k,
        "5d_K": _oxidation_5d_k,
        "main_group_K": _oxidation_main_group_k,
        "ln_L3": _oxidation_ln_l3,
        "an_L3": _oxidation_ln_l3,   # same white-line logic, An-flavored caveat
        "an_M": _oxidation_an_m,
        "5d_L3": _oxidation_5d_l3,
    }.get(family, _oxidation_unsupported)
    verdict = handler(descriptors, calibration, flags)
    verdict["element"] = element
    verdict["edge"] = edge_info.get("edge")
    verdict["family"] = family
    if descriptors.get("per_scan_trends", {}) and \
            descriptors["per_scan_trends"].get("drift_detected"):
        verdict["caveats"].append(
            "Per-scan descriptor drift detected — the averaged spectrum "
            "mixes evolving chemistry (possible beam damage); see "
            "per_scan_trends."
        )
    return verdict


def _oxidation_3d_k(descriptors: dict, calibration: dict, flags: list[str]) -> dict:
    element = (descriptors.get("edge") or {}).get("element")
    pre_rb = descriptors.get("pre_edge_rebroadened")
    pre_sharp = descriptors.get("pre_edge")

    pre = pre_rb if (pre_rb and pre_rb.get("fit_ok")) else None
    domain = "herfd_rebroadened"
    if pre is None and pre_sharp and pre_sharp.get("fit_ok"):
        pre, domain = pre_sharp, "herfd_sharp"

    # Fe has a conventional-XANES pre-edge centroid calibration (Wilke
    # 2001); every other K-edge falls through to the edge-shift path.
    if element == "Fe" and pre and pre.get("centroid_ev") is not None:
        return _oxidation_fe_pre_edge(descriptors, calibration, flags, pre, domain)
    return _oxidation_k_edge_shift(descriptors, calibration, flags, "3d_K")


def _oxidation_4d_k(descriptors: dict, calibration: dict, flags: list[str]) -> dict:
    return _oxidation_k_edge_shift(descriptors, calibration, flags, "4d_K")


def _oxidation_5d_k(descriptors: dict, calibration: dict, flags: list[str]) -> dict:
    return _oxidation_k_edge_shift(descriptors, calibration, flags, "5d_K")


def _oxidation_main_group_k(descriptors: dict, calibration: dict,
                            flags: list[str]) -> dict:
    """s/p-block K-edges (As, Se, Sn, ...): same edge-shift logic as the
    d-metal K path — the K edge still moves up with oxidation — with the
    generic-slope caveat carrying the extra main-group warning."""
    return _oxidation_k_edge_shift(descriptors, calibration, flags, "main_group_K")


def _oxidation_fe_pre_edge(descriptors: dict, calibration: dict,
                           flags: list[str], pre: dict, domain: str) -> dict:
    """Fe K pre-edge centroid on the Wilke 2001 CII axis (conventional domain).

    Under the assume-calibrated model ``offset_ev`` is 0.0 and the centroid
    is compared to the Wilke reference at face value (~0.2 eV systematic);
    a recorded calibration supplies a real offset instead.
    """
    e0 = descriptors["e0"]
    if domain == "herfd_sharp":
        flags = flags + ["calibration_domain_mismatch"]
    used = {
        "e0_ev": e0["e0_ev"], "e0_unc_ev": e0["e0_unc_ev"],
        "pre_edge_centroid_ev": pre.get("centroid_ev"),
        "pre_edge_centroid_unc_ev": pre.get("centroid_unc_ev"),
        "pre_edge_domain": domain,
    }
    v = _verdict("3d K-edge: pre-edge centroid (Wilke 2001 CII axis)",
                 used, calibration, flags,
                 {"method": "Wilke 2001 CII centroid axis"})

    offset = calibration["offset_ev"]
    cal_unc = calibration.get("measured_e0_unc_ev") or 0.05
    w = cal.WILKE_2001_FE_PRE_EDGE
    centroid_cal = pre["centroid_ev"] + offset
    x = (centroid_cal - w["centroid_fe2_ev"]) / w["centroid_separation_ev"]
    est = 2.0 + float(np.clip(x, 0.0, 1.0))
    unc_ev = float(np.sqrt(
        (pre.get("centroid_unc_ev") or 0.1) ** 2
        + w["centroid_separation_unc_ev"] ** 2 + cal_unc**2
    ))
    unc_val = unc_ev / w["centroid_separation_ev"]
    v["estimate"] = round(est, 2)
    v["range"] = [round(max(2.0, est - unc_val), 2),
                  round(min(3.0, est + unc_val), 2)]
    v["confidence"] = "medium"
    if domain == "herfd_sharp":
        v["confidence"] = "low"
        v["caveats"].append(
            "Wilke 2001 is a conventional-XANES calibration but only "
            "the sharp HERFD pre-edge fit was available (no core-hole "
            "width) — centroid may be biased."
        )
    if x < -0.25 or x > 1.25:
        v["confidence"] = _degrade(v["confidence"])
        v["caveats"].append(
            f"Calibrated centroid {centroid_cal:.2f} eV falls outside "
            "the Fe2+/Fe3+ calibration span — estimate clipped to [2, 3]."
        )
    if calibration.get("assumed"):
        v["caveats"].append(
            "Centroid placed on the Wilke axis under the assumed-foil-"
            "calibration model (no recorded offset, ~0.2 eV systematic "
            "folded in); a recorded Fe reference tightens it."
        )
    v["provenance"]["calibration_data"] = w["source"]
    v["caveats"].append(
        "Literature calibration, not site-matched measured standards "
        "(none exist yet — Phase 2); a single centroid cannot separate "
        "an intermediate valence from a mixture."
    )
    v["narration"] = (
        f"Fe K pre-edge centroid {centroid_cal:.2f} eV (calibrated, "
        f"{domain}) sits {centroid_cal - w['centroid_fe2_ev']:+.2f} eV "
        f"from the Fe2+ reference ({w['centroid_fe2_ev']} eV) on the "
        f"Wilke 2001 axis (Fe2+/Fe3+ separation "
        f"{w['centroid_separation_ev']} eV), indicating an average Fe "
        f"oxidation state of about {v['estimate']:+.2f} "
        f"(range {v['range'][0]}-{v['range'][1]})."
    )
    return v


# eV-per-valence edge-shift is the fallback for every K-edge without an
# Fe-style pre-edge calibration: non-Fe 3d, all 4d and 5d, and main-group
# K-edges.
_K_EDGE_SHELL = {"3d_K": "3d", "4d_K": "4d", "5d_K": "5d",
                 "main_group_K": "main-group"}

# Honesty gates for the edge-shift valence estimate. A chemical shift within
# one element is 1-3 eV/valence over at most ~6-8 valence units, so a shift
# beyond _MAX_PLAUSIBLE_SHIFT_EV is an anchor mismatch (wrong element/edge
# assignment, uncalibrated axis, or a tabulated-vs-measured E0-convention
# gap), never chemistry. An estimate whose uncertainty exceeds
# _MAX_ESTIMATE_UNC is narrated as position-only rather than as a number —
# "+6.6 units (range -2.2 to 15.3)" is worse than no number.
_MAX_PLAUSIBLE_SHIFT_EV = 10.0
_MAX_ESTIMATE_UNC = 2.0


def _shift_quality(shift: float) -> str:
    if shift > 1.0:
        return "consistent with an oxidized species"
    if shift < -1.0:
        return "consistent with a reduced or metallic-like species"
    return "close to the reference position"


def _oxidation_k_edge_shift(descriptors: dict, calibration: dict,
                            flags: list[str], family: str) -> dict:
    """Calibrated K-edge shift vs a reference E0 (non-Fe 3d / 4d / 5d).

    The reference anchor is, in order of preference, a measured
    same-element session reference (tightest), or — under the
    assume-calibrated model, where there usually is none — the tabulated
    edge energy, with the edge taken to sit at its theoretical position to
    within the ~0.2 eV foil-calibration systematic. Valence follows from
    the shift divided by an eV-per-valence slope (per-element if cited,
    else the generic 1-3 eV bracket).
    """
    edge_info = descriptors.get("edge") or {}
    element = edge_info.get("element")
    e0 = descriptors["e0"]
    offset = calibration["offset_ev"]
    cal_unc = calibration.get("measured_e0_unc_ev") or 0.05
    e0_cal = e0["e0_ev"] + offset
    shell = _K_EDGE_SHELL.get(family, "nd")

    used = {
        "e0_ev": e0["e0_ev"], "e0_unc_ev": e0["e0_unc_ev"],
        "e0_calibrated_ev": round(e0_cal, 2),
    }
    v = _verdict(f"{shell} K-edge: calibrated edge shift vs a reference E0",
                 used, calibration, flags,
                 {"method": "edge-shift-vs-reference (E0 position)"})

    same_ref = (calibration.get("element") == element
                and calibration.get("assigned_reference_ev") is not None)
    if same_ref:
        ref_ev = calibration["assigned_reference_ev"]
        ref_desc = f"the session {element} reference ({ref_ev:.1f} eV)"
    else:
        ref_ev = edge_info.get("tabulated_energy_ev")
        if ref_ev is None:
            v["confidence"] = "low"
            v["narration"] = (
                f"No reference anchor for {element} "
                f"{edge_info.get('edge')}: neither a same-element session "
                "reference nor a tabulated edge energy is available, so no "
                "valence number is assigned."
            )
            return v
        ref_desc = f"the tabulated {element} K edge ({ref_ev:.1f} eV)"
        v["caveats"].append(
            "Edge shift anchored on the tabulated edge energy under the "
            "assumed-foil-calibration model (axis foil-calibrated to "
            "~0.2 eV; edge taken at its theoretical position). The "
            "tabulated value is a compilation label carrying its own "
            "0.3-1 eV offset, so this is a coarse anchor — a recorded "
            "element-matched reference (record_energy_calibration) "
            "tightens it substantially."
        )

    shift = e0_cal - ref_ev
    direction = "above" if shift >= 0 else "below"
    energy_unc = float(np.hypot(e0.get("e0_unc_ev") or 0.05, cal_unc))
    used["edge_shift_ev"] = round(float(shift), 2)

    # Gate 1 — plausibility. A shift this large is never a chemical shift:
    # suspect a misidentified element/edge or an energy-axis problem.
    if abs(shift) > _MAX_PLAUSIBLE_SHIFT_EV:
        v["confidence"] = "refused"
        v["flags"].append("shift_implausible")
        v["narration"] = (
            f"{element} K edge measured at {e0_cal:.2f} eV, {shift:+.2f} eV "
            f"{direction} {ref_desc} — far beyond any chemical shift "
            f"(1-3 eV per valence unit). This indicates a misidentified "
            "element/edge, an uncalibrated energy axis, or an E0-convention "
            "mismatch, not chemistry. No valence is assigned; verify the "
            "edge assignment (pass element/edge explicitly) and the session "
            "energy calibration."
        )
        return v

    # Gate 2 — anchor honesty. The tabulated edge energy is a neutral-metal
    # compilation label (GENERIC_EDGE_SHIFT's own validity note forbids using
    # it as a shift anchor: an ordinary M(II) oxide sits several eV above
    # it). Without a same-element session reference, narrate the position
    # and the qualitative direction, never a valence number.
    if not same_ref:
        v["confidence"] = "low"
        v["flags"].append("no_session_reference")
        v["narration"] = (
            f"{element} K edge at {e0_cal:.2f} eV sits {shift:+.2f} eV "
            f"{direction} {ref_desc} — {_shift_quality(shift)}. No valence "
            "number is assigned against a tabulated anchor (a compilation "
            "label for the neutral element, not a valence reference): "
            "quantifying the oxidation state needs a same-element measured "
            "reference (record_energy_calibration, or LCF against measured "
            "standards)."
        )
        return v

    slope_entry = cal.PER_ELEMENT_EDGE_SHIFT.get(element or "")
    if slope_entry:
        slope = slope_entry["ev_per_valence"]
        est = shift / slope
        unc_val = energy_unc / slope
        v["provenance"]["calibration_data"] = slope_entry["source"]
    else:
        lo_s, hi_s = cal.GENERIC_EDGE_SHIFT["ev_per_valence_range"]
        mid = (lo_s + hi_s) / 2.0
        est = shift / mid
        # the 1-3 eV/valence slope range dominates; the energy term (E0 fit
        # + assumed 0.2 eV calibration) is folded in but is usually small.
        unc_val = float(np.hypot(
            max(abs(shift) / lo_s - abs(shift) / hi_s, 0.5), energy_unc / mid))
        v["provenance"]["calibration_data"] = cal.GENERIC_EDGE_SHIFT["source"]
        v["caveats"].append(cal.GENERIC_EDGE_SHIFT["note"])
        if family != "3d_K":
            v["caveats"].append(
                "The 1-3 eV/valence bracket is a 3d K-edge generalization; "
                f"{shell} K-edge chemical shifts per valence are typically "
                "smaller and more element-specific, so this is an "
                "order-of-magnitude guide only."
            )

    # Gate 3 — usefulness. If the uncertainty spans more than ~2 valence
    # units either way, a number misleads; report position + direction only.
    if unc_val > _MAX_ESTIMATE_UNC:
        v["confidence"] = "low"
        v["flags"].append("valence_estimate_unreliable")
        v["narration"] = (
            f"{element} K edge at {e0_cal:.2f} eV sits {shift:+.2f} eV "
            f"{direction} {ref_desc} — {_shift_quality(shift)}. The "
            f"valence conversion is suppressed: its uncertainty "
            f"(±{unc_val:.1f} units) exceeds what the shift can support. "
            "A cited per-element slope or LCF against measured standards "
            "is needed for a number."
        )
        return v

    # Gate 4 — physical clamp. Shifts vs a same-element reference cannot
    # exceed the element's valence span in magnitude.
    max_span = cal.MAX_VALENCE_SPAN.get(element or "", cal.DEFAULT_VALENCE_SPAN)
    lo = max(float(est - unc_val), -max_span)
    hi = min(float(est + unc_val), max_span)
    if abs(est) > max_span:
        v["confidence"] = "refused"
        v["flags"].append("shift_implausible")
        v["narration"] = (
            f"{element} K edge shift of {shift:+.2f} eV vs {ref_desc} "
            f"converts to {est:+.1f} valence units — outside the physically "
            f"possible span (±{max_span}) for {element}. Anchor or slope "
            "mismatch; no valence assigned."
        )
        return v

    v["estimate"] = round(float(est), 1)
    v["range"] = [round(lo, 1), round(hi, 1)]
    v["confidence"] = "low"
    v["caveats"].append(
        "Edge-shift-vs-reference valence is a coarse bracket "
        "(ligand/coordination dependent); pre-edge or LCF methods are "
        "preferred when available."
    )
    v["narration"] = (
        f"Calibrated {element} K edge at {e0_cal:.2f} eV sits "
        f"{shift:+.2f} eV {direction} {ref_desc}, indicating an oxidation "
        f"state about {v['estimate']:+.1f} unit(s) from that reference "
        f"(range {v['range'][0]} to {v['range'][1]})."
    )
    return v


def _oxidation_ln_l3(descriptors: dict, calibration: dict, flags: list[str]) -> dict:
    edge_info = descriptors.get("edge") or {}
    element = edge_info.get("element")
    wl = descriptors.get("white_line") or {}
    used = {
        "white_line_energy_ev": wl.get("white_line_energy_ev"),
        "white_line_height": wl.get("white_line_height"),
        "n_components": wl.get("n_components"),
        "components": wl.get("components"),
    }
    v = _verdict("Ln/An L3 white-line position and multi-peak structure",
                 used, calibration, flags,
                 {"method": "L3 white-line / final-state multi-peak analysis"})

    if element == "Ce" and wl.get("fit_ok") and wl.get("n_components", 0) >= 2:
        comps = sorted(wl["components"], key=lambda c: c["center_ev"])
        main = comps[0]
        upper = [c for c in comps[1:]
                 if 4.0 <= c["center_ev"] - main["center_ev"] <= 14.0]
        if upper:
            total = main["area"] + sum(c["area"] for c in upper)
            frac4 = sum(c["area"] for c in upper) / total if total > 0 else 0.0
            v["estimate"] = round(3.0 + frac4, 2)
            v["range"] = [round(max(3.0, v["estimate"] - 0.3), 2),
                          round(min(4.0, v["estimate"] + 0.3), 2)]
            v["confidence"] = "low"
            if "self_absorption_risk" in flags:
                v["caveats"].append(
                    "Fraction is area-ratio based; self-absorption damps "
                    "peaks unevenly — treat as qualitative."
                )
            v["provenance"]["calibration_data"] = cal.CE_L3["source"]
            v["caveats"].append(cal.CE_L3["note"] + " LCF against measured "
                                "Ce(III)/Ce(IV) standards (Phase 2) is the "
                                "quantitative route.")
            sep = upper[0]["center_ev"] - main["center_ev"]
            v["narration"] = (
                f"The Ce L3 white line resolves {len(comps)} components; a "
                f"higher-energy feature {sep:.1f} eV above the main line "
                f"matches the Ce(IV) 4f0/4f1L final-state doublet "
                f"(shape-based, calibration-independent). Area ratio gives "
                f"~{frac4:.0%} Ce(IV) character (average valence "
                f"~{v['estimate']:+.2f}), semi-quantitative."
            )
            return v

    v["confidence"] = "low"
    v["caveats"].append(
        f"No literature peak-position table for {element} L3 is encoded in "
        "v1; the calibrated white-line position is reported for comparison "
        "against session references or literature by the operator."
    )
    wl_cal = (wl.get("white_line_energy_ev") or 0) + calibration["offset_ev"]
    v["descriptors_used"]["white_line_energy_calibrated_ev"] = (
        round(wl_cal, 2) if wl.get("white_line_energy_ev") is not None else None
    )
    v["narration"] = (
        f"Calibrated {element} L3 white line at {wl_cal:.2f} eV. Higher "
        "oxidation states shift the white line to higher energy "
        f"({cal.L3_WHITE_LINE_TREND['source']}); no encoded reference "
        "table for this element, so no valence number is assigned."
    )
    return v


def _oxidation_an_m(descriptors: dict, calibration: dict, flags: list[str]) -> dict:
    edge_info = descriptors.get("edge") or {}
    element = edge_info.get("element")
    wl = descriptors.get("white_line") or {}
    used = {
        "main_peak_ev": wl.get("white_line_energy_ev"),
        "n_components": wl.get("n_components"),
        "components": wl.get("components"),
    }
    v = _verdict("Actinide M4 HERFD main-peak position and satellite structure",
                 used, calibration, flags,
                 {"method": "U M4 HERFD (Kvashnina/Butorin)",
                  "calibration_data": cal.U_M4_HERFD["source"]})

    satellites = []
    if wl.get("fit_ok") and wl.get("n_components", 0) >= 2:
        comps = sorted(wl["components"], key=lambda c: c["center_ev"])
        main = max(comps, key=lambda c: c["height"])
        satellites = [c for c in comps
                      if 1.5 <= c["center_ev"] - main["center_ev"] <= 7.0
                      and c["area"] >= 0.03 * main["area"]]

    if element == "U" and satellites:
        v["estimate"] = 6.0
        v["range"] = [5.5, 6.0]
        v["confidence"] = "medium"
        v["caveats"].append(
            "Satellite-based U(VI) assignment is shape-based "
            "(calibration-independent); mixed U(VI)/U(IV,V) fractions need "
            "LCF against measured standards (Phase 2)."
        )
        seps = ", ".join(f"+{s['center_ev'] - wl['white_line_energy_ev']:.1f}"
                         for s in satellites)
        v["narration"] = (
            f"The U M4 spectrum shows satellite structure ({seps} eV above "
            "the main line) characteristic of the uranyl U(VI) final-state "
            "pattern (Bes et al. 2016) — a calibration-independent shape "
            "signature."
        )
        return v

    if element == "U" and wl.get("white_line_energy_ev") is not None:
        peak_cal = wl["white_line_energy_ev"] + calibration["offset_ev"]
        table = cal.U_M4_HERFD["peak_positions_ev"]
        nearest = min(table.items(), key=lambda kv: abs(kv[1] - peak_cal))
        dist = abs(nearest[1] - peak_cal)
        valence = {"U4": 4, "U5": 5, "U6_main": 6}[nearest[0]]
        v["estimate"] = valence
        v["range"] = [valence - (1 if dist > 0.4 else 0),
                      valence + (1 if dist > 0.4 else 0)]
        v["confidence"] = "medium" if dist <= 0.4 else "low"
        v["caveats"].append(
            "Position-based assignment assumes the same Mbeta emission "
            "line and energy convention as the reference data "
            "(Bes et al. 2016); a mixed-valence sample averages positions."
        )
        v["narration"] = (
            f"Calibrated U M4 main peak at {peak_cal:.2f} eV lies "
            f"{dist:.2f} eV from the tabulated U({valence}) position "
            f"({nearest[1]} eV, Bes et al. 2016) — consistent with "
            f"U({valence}) within the stated caveats."
        )
        return v

    v["confidence"] = "low"
    v["narration"] = (
        f"No encoded M4 reference table for {element}; calibrated peak "
        "position reported in descriptors for operator comparison."
    )
    return v


def _oxidation_5d_l3(descriptors: dict, calibration: dict, flags: list[str]) -> dict:
    wl = descriptors.get("white_line") or {}
    used = {"white_line_energy_ev": wl.get("white_line_energy_ev"),
            "white_line_height": wl.get("white_line_height"),
            "white_line_area": wl.get("white_line_area")}
    v = _verdict("5d L3 white-line intensity (d-hole count trend)",
                 used, calibration, flags,
                 {"method": "L3 white-line trend",
                  "calibration_data": cal.L3_WHITE_LINE_TREND["source"]})
    v["confidence"] = "low"
    v["caveats"].append(cal.L3_WHITE_LINE_TREND["note"])
    if "self_absorption_risk" in flags:
        v["caveats"].append(
            "White-line intensity may be damped by self-absorption — the "
            "trend statement below can UNDERESTIMATE oxidation."
        )
    height = wl.get("white_line_height")
    v["narration"] = (
        (f"White-line height {height:.2f} (area-normalized units). "
         if height is not None else "")
        + "5d L3 white-line intensity tracks unoccupied d-states: higher "
        "oxidation gives a taller/higher-energy white line. v1 has no "
        "measured standards, so only this qualitative trend is reported."
    )
    return v


def _oxidation_unsupported(descriptors: dict, calibration: dict,
                           flags: list[str]) -> dict:
    v = _verdict("unsupported edge family", {}, calibration, flags, {})
    v["confidence"] = "refused"
    v["narration"] = (
        "This element/edge is outside the v1 interpretation scope "
        "(3d/4d/5d/main-group K, Ln/An L3, An M4/M5, 5d L3). Descriptors "
        "are still available from extract_xas_descriptors."
    )
    return v


# ---------------------------------------------------------------------------
# Coordination geometry
# ---------------------------------------------------------------------------

def interpret_coordination_geometry(descriptors: dict, calibration: dict) -> dict:
    edge_info = descriptors.get("edge") or {}
    family = edge_info.get("family", "other")
    element = edge_info.get("element")
    flags = list(descriptors.get("flags", []))

    # Pre-edge centrosymmetry readout applies to K-edges with a 1s->(n)d
    # pre-edge (3d/4d/5d K). Off Fe the Wilke intensity brackets are only
    # qualitative — the numeric span does not transfer (caveat below).
    if family not in ("3d_K", "4d_K", "5d_K"):
        wl = descriptors.get("white_line") or {}
        v = _verdict("L3/M white-line shape (electronic-structure hints only)",
                     {"white_line": {k: wl.get(k) for k in
                                     ("white_line_energy_ev", "white_line_height",
                                      "n_components")}},
                     calibration, flags,
                     {"method": "white-line covalency/d-hole trend"})
        v["confidence"] = "low"
        v["narration"] = (
            "Coordination-geometry readout via pre-edge centrosymmetry "
            "analysis applies to 3d/4d/5d K-edges; for this family only "
            "electronic-structure hints (white-line intensity/shape) are "
            "available, reported in descriptors."
        )
        v["element"], v["edge"], v["family"] = element, edge_info.get("edge"), family
        return v

    pre_rb = descriptors.get("pre_edge_rebroadened")
    pre_sharp = descriptors.get("pre_edge")
    pre = pre_rb if (pre_rb and pre_rb.get("fit_ok")) else None
    domain = "herfd_rebroadened"
    if pre is None and pre_sharp and pre_sharp.get("fit_ok"):
        pre, domain = pre_sharp, "herfd_sharp"
        flags = flags + ["calibration_domain_mismatch"]

    used = {
        "pre_edge_total_area": pre.get("total_area") if pre else None,
        "pre_edge_n_components": pre.get("n_components") if pre else None,
        "pre_edge_centroid_ev": pre.get("centroid_ev") if pre else None,
        "pre_edge_domain": domain if pre else None,
        "normalization": descriptors["provenance"]["normalization"].get("method"),
    }
    w = cal.WILKE_2001_FE_PRE_EDGE
    v = _verdict("3d K pre-edge intensity/centroid (Wilke CII envelope)",
                 used, calibration, flags,
                 {"method": "Wilke 2001 centroid-vs-intensity diagram",
                  "calibration_data": w["source"]})
    v["element"], v["edge"], v["family"] = element, edge_info.get("edge"), family

    if pre is None:
        v["confidence"] = "refused"
        v["narration"] = "No usable pre-edge fit — cannot assess site symmetry."
        return v

    # Coordination readout is intensity-based (calibration-independent in
    # energy) — allowed without a session calibration, but degraded by
    # intensity distortions.
    area = pre["total_area"]
    brackets = w["intensity_brackets"]
    if area < brackets["octahedral_max"]:
        geom = "centrosymmetric (octahedral-like)"
    elif area > brackets["tetrahedral_min"]:
        geom = "non-centrosymmetric (tetrahedral-like)"
    else:
        geom = "intermediate (5-coordinate / distorted / mixed)"
    v["estimate"] = geom
    v["confidence"] = "medium"
    if domain == "herfd_sharp":
        v["confidence"] = "low"
        v["caveats"].append(
            "Intensity envelope is a conventional-XANES calibration but "
            "only the sharp HERFD fit was available — intensities biased "
            "high."
        )
    if "self_absorption_risk" in flags:
        v["confidence"] = _degrade(v["confidence"])
        v["caveats"].append(
            "Self-absorption damps intensities (assume_dilute not "
            "asserted) — a truly tetrahedral site could read intermediate."
        )
    norm_prov = descriptors["provenance"]["normalization"]
    norm_method = norm_prov.get("method")
    if not norm_prov.get("applied") or norm_method != "area":
        v["confidence"] = _degrade(v["confidence"])
        v["caveats"].append(
            f"Intensity read on {norm_method} (not area) normalization — "
            "area normalization is preferred for HERFD intensities "
            "(Bugarin/Glatzel 2024)."
        )
    if element != "Fe":
        v["confidence"] = _degrade(v["confidence"])
        v["caveats"].append(
            f"Wilke envelope is calibrated for Fe; for {element} the "
            "centrosymmetry trend holds qualitatively but the numeric "
            "brackets do not transfer."
        )
    v["caveats"].append(brackets["note"])
    v["narration"] = (
        f"Integrated pre-edge intensity {area:.3f} ({domain}, "
        f"{used['normalization']}-normalized) with "
        f"{pre['n_components']} fitted component(s) indicates a "
        f"{geom} {element} site on the Wilke 2001 intensity axis "
        f"(octahedral < {brackets['octahedral_max']}, tetrahedral > "
        f"{brackets['tetrahedral_min']})."
    )
    return v


# ---------------------------------------------------------------------------
# Capstone summary
# ---------------------------------------------------------------------------

def summarize_chemistry(descriptors: dict, calibration: dict) -> dict:
    """Consolidated chemical interpretation + beam-damage drift verdict."""
    oxidation = interpret_oxidation_state(descriptors, calibration)
    coordination = interpret_coordination_geometry(descriptors, calibration)

    trends = descriptors.get("per_scan_trends")
    damage = {"assessed": trends is not None, "drift_detected": False}
    if trends:
        damage["drift_detected"] = trends.get("drift_detected", False)
        damage["drifting_metrics"] = trends.get("drifting_metrics", [])
        e0_t = trends.get("per_metric", {}).get("e0_ev", {})
        if e0_t.get("monotonic_drift"):
            direction = "reduction (photoreduction signature)" \
                if e0_t["theil_slope_per_scan"] < 0 else "oxidation"
            damage["e0_drift_ev_per_scan"] = e0_t["theil_slope_per_scan"]
            damage["direction"] = direction
            damage["note"] = (
                f"E0 drifts {e0_t['theil_slope_per_scan']:+.3f} eV/scan "
                f"(total {e0_t['predicted_total_change']:+.2f} eV over "
                f"{e0_t['n_scans']} scans) — monotonic shift toward "
                f"{direction}. Consider truncating to early scans and "
                "reducing dose."
            )

    sentences = [oxidation["narration"], coordination["narration"]]
    if damage.get("note"):
        sentences.append(damage["note"])
    elif trends is not None:
        sentences.append(
            "Per-scan descriptor trends show no monotonic drift — no "
            "beam-damage signature in E0, white line, or pre-edge."
        )

    return {
        "oxidation_state": oxidation,
        "coordination_geometry": coordination,
        "beam_damage": damage,
        "calibration_context": calibration,
        "flags": sorted(set(oxidation["flags"]) | set(coordination["flags"])),
        "narration": " ".join(s for s in sentences if s),
    }
