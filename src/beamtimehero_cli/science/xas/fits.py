"""Pseudo-Voigt peak fits over a XANES spectrum.

``fit_peak_region`` is the shared engine (BIC-selected component count with a
parsimony margin); ``fit_white_line`` and ``fit_pre_edge`` are the two windows
it is applied to. Fit windows come from :mod:`.policy`.
"""
from __future__ import annotations

import warnings

import numpy as np
from lmfit.models import LinearModel, PseudoVoigtModel, StepModel
from scipy.signal import find_peaks

from beamtimehero_cli.science.tables import edge_shifts as _edge_shifts
from beamtimehero_cli.science.xas.policy import (
    PRE_EDGE_WINDOW_REL,
    WHITE_LINE_WINDOW_REL,
)


_BIC_MARGIN = 10.0

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
# CITATIONS — method -> reference. ``None`` means the method is implemented
# but not yet attributed; those surface as gaps on the generated science
# index, and filling one in is a welcome contribution. See science/README.md.
# ---------------------------------------------------------------------------

CITATIONS = {
    "Wilke-style pre-edge fit (rising-edge atan baseline + pseudo-Voigts)":
        _edge_shifts.WILKE_2001_FE_PRE_EDGE["source"],
    "Component-count selection by BIC with a parsimony margin": None,
    "Pseudo-Voigt / step / linear models": "lmfit.models (Newville et al., lmfit).",
}
