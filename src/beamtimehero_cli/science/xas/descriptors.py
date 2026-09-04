"""The descriptor bundle — the source of truth the interpret_* tools consume.

``extract_descriptors`` runs the full pipeline (quality flags, normalization,
E0, pre-edge and white-line fits, per-scan drift trends) and returns a plain
dict of numbers with full provenance.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import kendalltau, theilslopes

from beamtimehero_cli.science.reduce import artifacts as quality
from beamtimehero_cli.science.xas.e0 import E0_DEFINITION, find_e0, rebroaden
from beamtimehero_cli.science.xas.fits import (
    fit_pre_edge,
    fit_white_line,
)
from beamtimehero_cli.science.xas.policy import (
    PRE_EDGE_WINDOW_REL,
    WHITE_LINE_WINDOW_REL,
)


# ---------------------------------------------------------------------------
# Per-scan descriptor trends (photoreduction / beam damage)
# ---------------------------------------------------------------------------

def _trend_stats(values: np.ndarray) -> dict:
    """Monotonic-drift test for one per-scan metric series.

    Kendall tau (monotonicity) + Theil-Sen slope (robust magnitude); the
    drift verdict requires BOTH statistical monotonicity (p < 0.05) and a
    predicted total change exceeding twice the residual scatter — a
    monotonic-but-negligible trend is not damage.
    """
    values = np.asarray(values, dtype=float)
    n = len(values)
    out = {"values": [float(v) for v in values], "n_scans": n}
    if n < 4 or np.allclose(values, values[0]):
        out.update({"monotonic_drift": False, "reason": "fewer than 4 scans or constant"})
        return out
    idx = np.arange(n, dtype=float)
    tau, p = kendalltau(idx, values)
    slope = theilslopes(values, idx)[0]
    resid = values - (values.mean() + slope * (idx - idx.mean()))
    noise = 1.4826 * np.median(np.abs(resid - np.median(resid)))
    total_change = slope * (n - 1)
    out.update({
        "kendall_tau": float(tau),
        "p_value": float(p),
        "theil_slope_per_scan": float(slope),
        "predicted_total_change": float(total_change),
        "residual_noise_mad": float(noise),
        "monotonic_drift": bool(p < 0.05 and abs(total_change) > 2 * noise),
    })
    return out


def per_scan_descriptor_trends(
    energy: np.ndarray,
    reps: np.ndarray,
    e0: float,
    white_line_energy: float | None,
    pre_edge_window: tuple[float, float] | None,
) -> dict:
    """Cheap, robust per-rep metrics + monotonic-drift tests.

    Metrics are deliberately fit-free (argmax/integrals) — a full peak fit
    per noisy single rep is fragile, and drift detection needs robustness
    more than absolute accuracy. Relative-only by construction: same mono
    axis for every rep, so no calibration is required.
    """
    energy = np.asarray(energy, dtype=float)
    reps = np.atleast_2d(np.asarray(reps, dtype=float))  # (n_scans, n_points)
    metrics: dict[str, list[float]] = {"e0_ev": []}
    if white_line_energy is not None:
        metrics["white_line_height"] = []
        metrics["white_line_energy_ev"] = []
    if pre_edge_window is not None:
        metrics["pre_edge_intensity"] = []

    wl_sel = None
    if white_line_energy is not None:
        wl_sel = (energy >= white_line_energy - 5) & (energy <= white_line_energy + 5)
        if wl_sel.sum() < 3:
            wl_sel = None
            metrics.pop("white_line_height")
            metrics.pop("white_line_energy_ev")
    pe_sel = None
    if pre_edge_window is not None:
        pe_sel = (energy >= pre_edge_window[0]) & (energy <= pre_edge_window[1])
        if pe_sel.sum() < 4:
            pe_sel = None
            metrics.pop("pre_edge_intensity")

    for row in reps:
        metrics["e0_ev"].append(find_e0(energy, row)["e0_ev"])
        if wl_sel is not None:
            seg = row[wl_sel]
            metrics["white_line_height"].append(float(np.max(seg)))
            metrics["white_line_energy_ev"].append(float(energy[wl_sel][np.argmax(seg)]))
        if pe_sel is not None:
            e_pe, y_pe = energy[pe_sel], row[pe_sel]
            baseline = np.interp(e_pe, [e_pe[0], e_pe[-1]], [y_pe[0], y_pe[-1]])
            metrics["pre_edge_intensity"].append(
                float(np.trapezoid(y_pe - baseline, e_pe))
            )

    trends = {name: _trend_stats(np.array(vals)) for name, vals in metrics.items()}
    drifting = [name for name, t in trends.items() if t.get("monotonic_drift")]
    return {
        "per_metric": trends,
        "drifting_metrics": drifting,
        "drift_detected": bool(drifting),
        "method": (
            "per-scan trend analysis (Kendall tau p<0.05 AND |Theil-Sen "
            "total change| > 2x residual MAD) — catches monotonic "
            "photoreduction a first-half/second-half split can hide"
        ),
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def extract_descriptors(
    energy: np.ndarray,
    mu: np.ndarray,
    reps: np.ndarray | None = None,
    edge_info: dict | None = None,
    normalization: str = "area",
    assume_dilute: bool | None = None,
    white_line_components: int = 1,
    pre_edge_window_rel: tuple[float, float] = PRE_EDGE_WINDOW_REL,
) -> tuple[dict, dict]:
    """Full descriptor extraction. Returns ``(descriptors, arrays)``.

    ``descriptors`` is JSON-ready; ``arrays`` holds the numeric curves
    (spectrum, fits, windows) for plotting only. When ``edge_info``
    includes a core-hole width and a 3d/4d/5d K-edge family, a re-broadened
    pre-edge fit is computed alongside the sharp one so conventional-
    domain calibrations (Wilke) have a valid input.
    """
    from beamtimehero_cli.science.xas import normalize as norm

    energy = np.asarray(energy, dtype=float)
    mu = np.asarray(mu, dtype=float)
    flags: list[str] = []

    glitch_mask = quality.detect_glitches(energy, mu)
    if glitch_mask.any():
        mu = quality.interpolate_over_mask(energy, mu, glitch_mask)
        flags.append("glitch_masked")
    saturation = quality.detect_saturation(mu)
    if saturation["saturated"]:
        flags.append("saturation_suspected")
    self_abs = quality.self_absorption_assessment(assume_dilute)
    if self_abs["risk"] == "unknown":
        flags.append("self_absorption_risk")

    e0_info = find_e0(energy, mu)
    e0 = e0_info["e0_ev"]

    if normalization == "area":
        mu_n, norm_prov = norm.area_normalize(energy, mu, e0)
        if not norm_prov.get("applied"):
            flags.append("area_normalization_unavailable")
    elif normalization == "mback":
        einfo = edge_info or {}
        mu_n, norm_prov = norm.mback_normalize(
            energy, mu, e0, einfo.get("element"), einfo.get("edge")
        )
        if not norm_prov.get("applied"):
            flags.append("mback_normalization_unavailable")
    else:
        mu_n, norm_prov = mu, norm.edge_step_provenance()

    white_line = fit_white_line(energy, mu_n, e0, max_components=white_line_components)
    pre_edge = fit_pre_edge(energy, mu_n, e0, window_rel=pre_edge_window_rel)

    family = (edge_info or {}).get("family")
    core_width = (edge_info or {}).get("core_hole_width_ev")
    pre_edge_rebroadened = None
    # 3d/4d/5d K-edges all carry a 1s->(n)d pre-edge; the heavier K-edges
    # have LARGER 1s core-hole widths, so a HERFD spectrum needs
    # re-broadening even more before a conventional-domain (Wilke)
    # calibration applies.
    if family in ("3d_K", "4d_K", "5d_K") and core_width and pre_edge.get("fit_ok"):
        mu_broad = rebroaden(energy, mu_n, core_width)
        pre_edge_rebroadened = fit_pre_edge(energy, mu_broad, e0,
                                            window_rel=pre_edge_window_rel)
        if pre_edge_rebroadened.get("fit_ok"):
            pre_edge_rebroadened["provenance"]["calibration_domain"] = "herfd_rebroadened"
            pre_edge_rebroadened["provenance"]["rebroadened_fwhm_ev"] = core_width

    trends = None
    if reps is not None and len(np.atleast_2d(reps)) >= 4:
        trends = per_scan_descriptor_trends(
            energy, reps, e0,
            white_line.get("white_line_energy_ev") if white_line.get("fit_ok") else None,
            (e0 + pre_edge_window_rel[0], e0 + pre_edge_window_rel[1]),
        )
        if trends["drift_detected"]:
            flags.append("per_scan_drift")

    arrays = {
        "energy": energy, "mu": mu_n, "glitch_mask": glitch_mask,
        "white_line": white_line.pop("_arrays", None),
        "pre_edge": pre_edge.pop("_arrays", None),
        "pre_edge_rebroadened": (
            pre_edge_rebroadened.pop("_arrays", None) if pre_edge_rebroadened else None
        ),
    }

    descriptors = {
        "e0": e0_info,
        "edge": edge_info,
        "white_line": white_line,
        "pre_edge": pre_edge,
        "pre_edge_rebroadened": pre_edge_rebroadened,
        "per_scan_trends": trends,
        "quality": {"saturation": saturation, "self_absorption": self_abs,
                    "n_glitch_points": int(glitch_mask.sum())},
        "provenance": {
            "normalization": norm_prov,
            "e0_definition": E0_DEFINITION,
            "herfd_caveat": (
                "HERFD is a constant-emission-energy cut through the RIXS "
                "plane, not the absorption cross-section: intensities "
                "depend on the emission line and are not comparable across "
                "emission lines or to conventional-XANES calibrations "
                "without re-broadening."
            ),
        },
        "flags": flags,
    }
    return descriptors, arrays
