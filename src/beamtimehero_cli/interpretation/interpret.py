"""Hybrid interpretation engine: descriptors -> structured chemical verdicts.

Every verdict follows one output contract:

    {estimate, range, confidence, basis, descriptors_used,
     calibration_context, flags, provenance, caveats, narration}

with ``confidence`` in {high, medium, low, refused}. The narration is
assembled from the computed numbers — never invented. The rigor gates:

- Absolute oxidation states from POSITIONS (edge, centroid, peak) require
  a session energy calibration; without one the tools refuse the absolute
  call (``refused_absolute: true``) and report calibration-independent
  content only (shapes, relative per-scan trends, descriptors).
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


def _uncalibrated_refusal(v: dict, what: str) -> None:
    v["confidence"] = "refused"
    v["refused_absolute"] = True
    v["caveats"].append(
        f"No session energy calibration: an absolute {what} cannot be "
        "stated. Monochromator offset/drift is eV-scale — the same size "
        "as the valence signal. Record a reference-foil calibration "
        "(record_energy_calibration), or compare spectra measured in this "
        "session relative to each other."
    )


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
    e0 = descriptors["e0"]

    pre = pre_rb if (pre_rb and pre_rb.get("fit_ok")) else None
    domain = "herfd_rebroadened"
    if pre is None and pre_sharp and pre_sharp.get("fit_ok"):
        pre = pre_sharp
        domain = "herfd_sharp"
        flags = flags + ["calibration_domain_mismatch"]

    used = {
        "e0_ev": e0["e0_ev"], "e0_unc_ev": e0["e0_unc_ev"],
        "pre_edge_centroid_ev": pre.get("centroid_ev") if pre else None,
        "pre_edge_centroid_unc_ev": pre.get("centroid_unc_ev") if pre else None,
        "pre_edge_domain": domain if pre else None,
    }
    v = _verdict("3d K-edge: pre-edge centroid (+ calibrated edge shift)",
                 used, calibration, flags, {"method": "Wilke 2001 CII centroid axis"})

    if not calibration.get("calibrated"):
        _uncalibrated_refusal(v, "oxidation state (edge/centroid position)")
        parts = []
        if pre and pre.get("centroid_ev") is not None:
            parts.append(
                f"pre-edge centroid at {pre['centroid_ev']:.2f} eV "
                f"(uncalibrated mono axis, {domain})"
            )
        parts.append(f"E0({e0['e0_definition'].split(' ')[0]}) at {e0['e0_ev']:.2f} eV (uncalibrated)")
        v["narration"] = (
            "Absolute oxidation state refused: no session energy "
            "calibration. Calibration-independent content: " + "; ".join(parts) + "."
        )
        return v

    offset = calibration["offset_ev"]
    cal_unc = calibration.get("measured_e0_unc_ev") or 0.05

    if element == "Fe" and pre and pre.get("centroid_ev") is not None:
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

    # Non-Fe 3d metal (or no usable pre-edge): calibrated edge shift vs a
    # same-element session reference.
    e0_cal = e0["e0_ev"] + offset
    same_ref = (calibration.get("element") == element)
    slope_entry = cal.PER_ELEMENT_EDGE_SHIFT.get(element or "")
    if not same_ref:
        v["confidence"] = "low"
        v["caveats"].append(
            f"Session calibration used a {calibration.get('element')} "
            f"{calibration.get('edge')} reference, not {element}: the mono "
            "offset is energy-dependent, so transferring it across edges "
            "adds unquantified error. Treat the shift as approximate."
        )
        v["estimate"] = None
        v["range"] = None
        v["narration"] = (
            f"Calibrated E0 = {e0_cal:.2f} eV (offset {offset:+.2f} eV from "
            f"a {calibration.get('element')} reference). No same-element "
            "session reference exists, so no defensible valence number — "
            "measure an element-matched reference to enable it."
        )
        return v

    ref_ev = calibration["assigned_reference_ev"]
    shift = e0_cal - ref_ev
    if slope_entry:
        slope = slope_entry["ev_per_valence"]
        est = shift / slope
        v["provenance"]["calibration_data"] = slope_entry["source"]
    else:
        lo_s, hi_s = cal.GENERIC_EDGE_SHIFT["ev_per_valence_range"]
        est = shift / ((lo_s + hi_s) / 2)
        v["provenance"]["calibration_data"] = cal.GENERIC_EDGE_SHIFT["source"]
        v["caveats"].append(cal.GENERIC_EDGE_SHIFT["note"])
    unc_val = max(abs(shift) / 1.0 - abs(shift) / 3.0, 0.5)  # slope-range dominated
    v["estimate"] = round(float(est), 1)
    v["range"] = [round(float(est - unc_val), 1), round(float(est + unc_val), 1)]
    v["confidence"] = "low"
    v["caveats"].append(
        "Edge-shift-vs-metal-foil valence is a coarse bracket "
        "(ligand/coordination dependent); pre-edge or LCF methods are "
        "preferred when available."
    )
    v["narration"] = (
        f"Calibrated {element} K edge at {e0_cal:.2f} eV is shifted "
        f"{shift:+.2f} eV from the session {element} reference "
        f"({ref_ev:.1f} eV), suggesting an oxidation state above the "
        f"reference by roughly {v['estimate']:+.1f} units "
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

    if not calibration.get("calibrated"):
        _uncalibrated_refusal(v, "valence from white-line position")
        single = wl.get("white_line_energy_ev")
        v["narration"] = (
            "Absolute valence refused (no session energy calibration) and "
            "no calibration-independent multi-peak signature resolved. "
            + (f"White line at {single:.2f} eV on the uncalibrated axis; "
               if single is not None else "")
            + "relative comparisons between this session's spectra remain valid."
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

    if not calibration.get("calibrated"):
        _uncalibrated_refusal(v, "actinide valence from M4 peak position")
        v["narration"] = (
            "No U(VI) satellite signature resolved and no session energy "
            "calibration — the absolute M4 peak position cannot be "
            "compared to the U(IV)/U(V)/U(VI) reference positions."
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
        "(3d K, Ln/An L3, An M4/M5, 5d L3). Descriptors are still "
        "available from extract_xas_descriptors."
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

    if family != "3d_K":
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
            "analysis applies to 3d K-edges; for this family only "
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
    if not descriptors["provenance"]["normalization"].get("applied") or \
            descriptors["provenance"]["normalization"].get("method") != "area":
        v["confidence"] = _degrade(v["confidence"])
        v["caveats"].append(
            "Intensity read on edge-step (not area) normalization — "
            "known HERFD intensity bias (Bugarin/Glatzel 2024)."
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
