"""Numeric spectral descriptors from a normalized mu(E) XANES spectrum.

Backend-agnostic like ``analysis/xas.py``: arrays in, dicts out, no I/O.
Every fitted quantity carries an uncertainty from the fit covariance and
a provenance record (baseline model, fit range, component count) — the
same spectrum must yield the same numbers, and downstream verdicts must
be able to gate on how well-determined those numbers are.

E0 definitions are explicit and fixed:

- ``derivative_max`` — energy of the maximum of the Savitzky-Golay
  smoothed first derivative (parabola-refined). The primary definition;
  the session calibration record uses the same one.
- ``half_step`` — energy where the edge-step-normalized spectrum first
  crosses 0.5 near the rising edge. Reported for cross-checks only;
  never mix definitions when computing shifts.
"""
from __future__ import annotations

import warnings

import numpy as np
from lmfit.models import LinearModel, PseudoVoigtModel, StepModel
from scipy.signal import find_peaks, savgol_filter
from scipy.stats import kendalltau, theilslopes

from beamtimehero_cli.interpretation import quality

E0_DEFINITION = "derivative_max (Savitzky-Golay smoothed, parabola-refined)"

# Fixed, logged fit-window defaults (eV relative to derivative-max E0).
# The pre-edge window tops out 5 eV below E0: 3d pre-edge centroids sit
# 6-13 eV below the derivative maximum, while any closer approach lets
# the rising edge leak spurious components into the centroid/area.
PRE_EDGE_WINDOW_REL = (-20.0, -5.0)
WHITE_LINE_WINDOW_REL = (-10.0, 40.0)

# BIC parsimony: an extra pre-edge component must improve BIC by this
# much to be accepted ("strong evidence" on the conventional BIC scale).
_BIC_MARGIN = 10.0


# ---------------------------------------------------------------------------
# Grid helpers
# ---------------------------------------------------------------------------

def _uniform(energy: np.ndarray, mu: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Interpolate onto a uniform grid (median step) for filters/convolution."""
    energy = np.asarray(energy, dtype=float)
    mu = np.asarray(mu, dtype=float)
    step = float(np.median(np.diff(energy)))
    if step <= 0:
        raise ValueError("Energy axis must be strictly increasing.")
    e_u = np.arange(energy[0], energy[-1] + step / 2, step)
    return e_u, np.interp(e_u, energy, mu), step


def _odd_window_points(step: float, span_ev: float, n: int) -> int:
    pts = max(5, int(round(span_ev / step)) | 1)
    return min(pts, (n - 1) | 1 if (n - 1) % 2 else (n - 2) | 1)


# ---------------------------------------------------------------------------
# E0
# ---------------------------------------------------------------------------

def find_e0(energy: np.ndarray, mu: np.ndarray, smooth_span_ev: float = 2.0) -> dict:
    """Edge position under both fixed definitions, with uncertainty.

    The derivative-max uncertainty combines the grid half-step floor with
    the parabola-refinement curvature; it does NOT include the energy-
    calibration systematic (that lives in the calibration record).
    """
    e_u, mu_u, step = _uniform(energy, mu)
    window = _odd_window_points(step, smooth_span_ev, len(e_u))
    deriv = savgol_filter(mu_u, window_length=window, polyorder=2, deriv=1, delta=step)
    i = int(np.argmax(deriv))

    e0 = float(e_u[i])
    unc = step / 2.0
    if 0 < i < len(e_u) - 1:
        y0, y1, y2 = deriv[i - 1], deriv[i], deriv[i + 1]
        denom = y0 - 2 * y1 + y2
        if denom < 0:  # proper maximum
            shift = 0.5 * (y0 - y2) / denom
            e0 = float(e_u[i] + np.clip(shift, -1, 1) * step)

    # half-step: first upward 0.5-crossing within a few smoothing spans of e0
    e0_half = None
    near = (e_u > e0 - 5 * smooth_span_ev) & (e_u < e0 + 5 * smooth_span_ev)
    idx = np.where(near & (mu_u >= 0.5))[0]
    if len(idx) and idx[0] > 0:
        j = idx[0]
        y_lo, y_hi = mu_u[j - 1], mu_u[j]
        if y_hi > y_lo:
            e0_half = float(e_u[j - 1] + (0.5 - y_lo) / (y_hi - y_lo) * step)

    return {
        "e0_ev": e0,
        "e0_unc_ev": float(unc),
        "e0_definition": E0_DEFINITION,
        "e0_half_step_ev": e0_half,
        "grid_step_ev": step,
        "smooth_span_ev": smooth_span_ev,
    }


# ---------------------------------------------------------------------------
# Core-hole re-broadening (HERFD -> conventional calibration domain)
# ---------------------------------------------------------------------------

def rebroaden(energy: np.ndarray, mu: np.ndarray, fwhm_ev: float) -> np.ndarray:
    """Convolve a HERFD spectrum with a Lorentzian of the core-hole width.

    Puts lifetime-sharpened HERFD data on the same footing as
    conventional-XANES calibrations (e.g. Wilke 2001) before those
    calibrations are applied. Returns mu on the input grid.
    """
    if fwhm_ev <= 0:
        return np.asarray(mu, dtype=float)
    e_u, mu_u, step = _uniform(energy, mu)
    hwhm = fwhm_ev / 2.0
    k = int(np.ceil(40 * hwhm / step))
    x = np.arange(-k, k + 1) * step
    kernel = hwhm / (np.pi * (x**2 + hwhm**2))
    kernel /= kernel.sum()
    padded = np.concatenate([np.full(k, mu_u[0]), mu_u, np.full(k, mu_u[-1])])
    broadened = np.convolve(padded, kernel, mode="same")[k:-k]
    return np.interp(energy, e_u, broadened)


# ---------------------------------------------------------------------------
# Peak-region fitting (shared by pre-edge and white-line/multi-peak)
# ---------------------------------------------------------------------------

def _initial_peak_centers(e: np.ndarray, y: np.ndarray, n: int) -> np.ndarray:
    """Seed peak centers from local maxima of the detrended window.

    A uniform spread lets far-from-truth components collapse to zero
    amplitude and the fit converge to baseline-only; seeding at the
    actual bumps makes convergence deterministic.
    """
    detrended = y - np.interp(e, [e[0], e[-1]], [y[0], y[-1]])
    prominence = max(0.02 * (np.max(detrended) - np.min(detrended)), 1e-6)
    peaks, props = find_peaks(detrended, prominence=prominence)
    if len(peaks):
        order = np.argsort(props["prominences"])[::-1]
        centers = list(e[peaks[order][:n]])
    else:
        centers = [float(e[int(np.argmax(detrended))])]
    span = e[-1] - e[0]
    while len(centers) < n:  # remaining components near the strongest bump
        centers.append(centers[0] + (len(centers)) * span / (2 * n)
                       * (1 if len(centers) % 2 else -1))
    return np.clip(np.sort(np.array(centers[:n])), e[0], e[-1])

def fit_peak_region(
    energy: np.ndarray,
    mu: np.ndarray,
    window: tuple[float, float],
    max_components: int = 3,
    baseline_form: str = "atan",
    edge_center_hint: float | None = None,
    edge_center_bounds: tuple[float, float] | None = None,
) -> dict:
    """Fit baseline (step + line) plus 1..max_components pseudo-Voigts.

    Component count is chosen by BIC with a parsimony margin: an extra
    peak must lower BIC by >= 10 to be kept, and the choice is flagged
    ambiguous when the runner-up is within that margin. Baseline model,
    window, and component count are all reported — pre-edge results are
    known to be sensitive to these choices, so they are provenance, not
    internals.
    """
    energy = np.asarray(energy, dtype=float)
    mu = np.asarray(mu, dtype=float)
    sel = (energy >= window[0]) & (energy <= window[1])
    e, y = energy[sel], mu[sel]
    if len(e) < 8 + 3 * 1:
        return {"fit_ok": False, "error": f"only {len(e)} points in window {window}"}

    span = window[1] - window[0]
    hint = edge_center_hint if edge_center_hint is not None else window[1] + 5.0
    # Pre-edge fits model the tail of a rising edge ABOVE the window;
    # white-line fits contain the edge step inside the window. Callers pick.
    ec_lo, ec_hi = edge_center_bounds or (window[1], window[1] + 25)
    hint = float(np.clip(hint, ec_lo, ec_hi))

    fits = {}
    for n in range(1, max_components + 1):
        if len(e) < 8 + 3 * n:
            break
        model = StepModel(form=baseline_form, prefix="edge_") + LinearModel(prefix="lin_")
        params = model.make_params(
            edge_amplitude=max(y[-1], 0.1), edge_center=hint, edge_sigma=2.0,
            lin_slope=0.0, lin_intercept=float(np.min(y)),
        )
        params["edge_amplitude"].set(min=0, max=5)
        params["edge_center"].set(min=ec_lo, max=ec_hi)
        params["edge_sigma"].set(min=0.3, max=15)

        peak_es = _initial_peak_centers(e, y, n)
        amp0 = max((np.max(y) - np.min(y)) * 1.0, 1e-3)
        for i, pe in enumerate(peak_es):
            pv = PseudoVoigtModel(prefix=f"p{i}_")
            model = model + pv
            params.update(pv.make_params(center=pe, amplitude=amp0, sigma=0.7, fraction=0.5))
            params[f"p{i}_center"].set(min=window[0], max=window[1])
            params[f"p{i}_sigma"].set(min=0.15, max=span / 2)
            params[f"p{i}_amplitude"].set(min=0)
            params[f"p{i}_fraction"].set(min=0, max=1)
        try:
            # TRF handles the box bounds natively — converges in O(100)
            # evals where the default leastsq stalls against the bounds.
            # A singular covariance (an undetermined component) makes lmfit
            # warn on sqrt(negative); we coerce those stderrs to None in
            # _p() below, so silence the noise for clean beamline logs.
            with np.errstate(invalid="ignore"), warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                fits[n] = model.fit(y, params, x=e,
                                    method="least_squares", max_nfev=5000)
        except Exception as exc:  # lmfit can raise on degenerate data
            fits[n] = None
            if n == 1:
                return {"fit_ok": False, "error": f"fit failed: {exc}"}
            break

    valid = {n: f for n, f in fits.items() if f is not None and np.isfinite(f.bic)}
    if not valid:
        return {"fit_ok": False, "error": "no component count produced a finite fit"}
    best_bic = min(f.bic for f in valid.values())
    chosen_n = min(n for n, f in valid.items() if f.bic <= best_bic + _BIC_MARGIN)
    result = valid[chosen_n]
    ambiguous = sum(1 for f in valid.values() if f.bic <= best_bic + _BIC_MARGIN) > 1

    def _p(name, comp):
        par = result.params[f"{comp}_{name}"]
        stderr = par.stderr
        if stderr is None or not np.isfinite(stderr):
            stderr = None  # singular covariance -> undetermined, not NaN
        else:
            stderr = float(stderr)
        return float(par.value), stderr

    all_components = []
    for i in range(chosen_n):
        c, c_u = _p("center", f"p{i}")
        a, a_u = _p("amplitude", f"p{i}")  # lmfit PV amplitude == area
        all_components.append({
            "center_ev": c, "center_unc_ev": c_u,
            "area": a, "area_unc": a_u,
            "fwhm_ev": float(result.params[f"p{i}_fwhm"].value),
            "height": float(result.params[f"p{i}_height"].value),
        })

    # Components pinned at the window boundary are baseline/edge-leak
    # artifacts, near-zero-area components are BIC overfitting relics, and
    # components wider than half the window are baseline pedestals, not
    # spectral features — all are excluded from centroid/intensity (and
    # reported as excluded).
    raw_total = sum(c["area"] for c in all_components)
    margin = 0.75
    components, excluded = [], []
    for c in all_components:
        boundary = (c["center_ev"] <= window[0] + margin
                    or c["center_ev"] >= window[1] - margin)
        insignificant = raw_total > 0 and c["area"] < 0.02 * raw_total
        too_broad = c["fwhm_ev"] > 0.5 * span
        (excluded if boundary or insignificant or too_broad else components).append(c)
    if not components and all_components:
        components = [max(all_components, key=lambda c: c["area"])]
        excluded = [c for c in all_components if c is not components[0]]

    total_area = sum(c["area"] for c in components)
    centroid = centroid_unc = None
    if total_area > 0:
        centroid = sum(c["area"] * c["center_ev"] for c in components) / total_area
        var = 0.0
        determined = True
        for c in components:
            w = c["area"] / total_area
            if c["center_unc_ev"] is None or c["area_unc"] is None:
                determined = False
                break
            var += (w * c["center_unc_ev"]) ** 2
            var += (((c["center_ev"] - centroid) / total_area) * c["area_unc"]) ** 2
        centroid_unc = float(np.sqrt(var)) if determined else None

    fit_curve = result.best_fit
    r_factor = float(np.sum((y - fit_curve) ** 2) / max(np.sum(y**2), 1e-30))

    return {
        "fit_ok": True,
        "n_components": len(components),
        "n_components_fitted": chosen_n,
        "n_components_ambiguous": ambiguous,
        "components": components,
        "excluded_components": excluded,
        "centroid_ev": centroid,
        "centroid_unc_ev": centroid_unc,
        "total_area": total_area,
        "r_factor": r_factor,
        "reduced_chi2": float(result.redchi),
        "bic_by_n": {n: float(f.bic) for n, f in valid.items()},
        "provenance": {
            "baseline_model": f"step({baseline_form}) + linear",
            "fit_window_ev": [float(window[0]), float(window[1])],
            "component_model": "pseudo-Voigt (lmfit; amplitude == area)",
            "selection": f"BIC with +{_BIC_MARGIN} parsimony margin",
        },
        "_arrays": {
            "e": e, "y": y, "fit": fit_curve,
            "baseline": result.eval_components(x=e)["edge_"]
            + result.eval_components(x=e)["lin_"],
        },
    }


def fit_white_line(energy: np.ndarray, mu: np.ndarray, e0: float,
                   max_components: int = 1) -> dict:
    """White-line fit: erf edge step + pseudo-Voigt(s) above E0.

    ``max_components > 1`` enables the multi-peak path required for Ce L3
    (Ce(IV) final-state doublet) and U(VI) satellite structure.
    """
    window = (e0 + WHITE_LINE_WINDOW_REL[0], e0 + WHITE_LINE_WINDOW_REL[1])
    window = (max(window[0], float(energy[0])), min(window[1], float(energy[-1])))
    fit = fit_peak_region(
        energy, mu, window, max_components=max_components,
        baseline_form="erf", edge_center_hint=e0,
        edge_center_bounds=(e0 - 5.0, e0 + 5.0),
    )
    if not fit.get("fit_ok"):
        return fit
    # main line by HEIGHT, not area — a broad low background component can
    # out-area the actual white line
    main = max(fit["components"], key=lambda c: c["height"])
    fit["white_line_energy_ev"] = main["center_ev"]
    fit["white_line_energy_unc_ev"] = main["center_unc_ev"]
    fit["white_line_height"] = main["height"]
    fit["white_line_area"] = main["area"]
    return fit


def fit_pre_edge(energy: np.ndarray, mu: np.ndarray, e0: float,
                 window_rel: tuple[float, float] = PRE_EDGE_WINDOW_REL,
                 max_components: int = 3) -> dict:
    """Wilke-style pre-edge fit: rising-edge (atan) baseline + 1-3 pseudo-Voigts."""
    window = (e0 + window_rel[0], e0 + window_rel[1])
    if window[0] < float(energy[0]) + 1.0:
        window = (float(energy[0]) + 1.0, window[1])
    return fit_peak_region(
        energy, mu, window, max_components=max_components,
        baseline_form="atan", edge_center_hint=e0,
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
    includes a core-hole width and a 3d K-edge family, a re-broadened
    pre-edge fit is computed alongside the sharp one so conventional-
    domain calibrations (Wilke) have a valid input.
    """
    from beamtimehero_cli.interpretation import normalize as norm

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
    else:
        mu_n, norm_prov = mu, norm.edge_step_provenance()

    white_line = fit_white_line(energy, mu_n, e0, max_components=white_line_components)
    pre_edge = fit_pre_edge(energy, mu_n, e0, window_rel=pre_edge_window_rel)

    family = (edge_info or {}).get("family")
    core_width = (edge_info or {}).get("core_hole_width_ev")
    pre_edge_rebroadened = None
    if family == "3d_K" and core_width and pre_edge.get("fit_ok"):
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
