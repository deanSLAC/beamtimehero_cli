"""Cross-spectrum comparison: energy registration, differences, and LCF.

``align_spectra`` and ``difference_spectrum`` register spectra by their E0
before comparing, so a difference reflects spectral shape rather than a
calibration offset. ``compare_to_references`` is the axis-agnostic
non-negative linear-combination fit (usable on mu(E), energy loss, or k).
"""
from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Cross-file energy registration + difference spectra
# ---------------------------------------------------------------------------

# A per-spectrum E0 shift beyond this is find_e0 latching onto a glitch, not
# mono drift — refuse it rather than smear the comparison. Ported from the
# chemcatal portal's xas_core MAX_ALIGN_SHIFT_EV guard.
MAX_ALIGN_SHIFT_EV = 10.0


def align_spectra(spectra, target_e0=None, max_shift_ev=MAX_ALIGN_SHIFT_EV):
    """Shift spectra in energy so their E0s coincide — registration by report.

    ``spectra`` is a list of ``(energy, mu)`` array pairs. Each spectrum's E0
    is the derivative maximum (``interpretation.descriptors.find_e0``); the
    target is ``target_e0`` (eV) when given, else the FIRST spectrum's E0.

    Returns one dict per input::

        {energy (shifted), mu, e0_before, shift_applied, e0_after,
         refused, note, target_e0, target_source}

    A proposed shift whose magnitude exceeds *max_shift_ev* is REFUSED
    (``shift_applied=0``, ``refused=True``) — beyond plausible mono drift the
    E0 fit latched onto a glitch, and shifting would corrupt the comparison.
    Nothing is written anywhere; callers report the shifts.

    Raises ValueError when no spectrum yields an E0 to anchor to.
    """
    from beamtimehero_cli.science.xas.e0 import find_e0

    pairs = [(np.asarray(e, dtype=float), np.asarray(m, dtype=float))
             for e, m in spectra]
    e0s: list[float | None] = []
    for energy, mu in pairs:
        try:
            e0s.append(float(find_e0(energy, mu)["e0_ev"]))
        except Exception:  # noqa: BLE001 — un-fittable spectra stay unshifted
            e0s.append(None)

    if target_e0 is not None:
        target = float(target_e0)
        target_source = "explicit target_e0"
    else:
        target = next((e0 for e0 in e0s if e0 is not None), None)
        target_source = "first spectrum's E0"
        if target is None:
            raise ValueError(
                "Could not determine E0 for any spectrum — nothing to align to."
            )

    out = []
    for (energy, mu), e0 in zip(pairs, e0s):
        refused = False
        note = None
        if e0 is None:
            shift = 0.0
            refused = True
            note = "E0 could not be fit for this spectrum; left unshifted."
        else:
            shift = target - e0
            if abs(shift) > max_shift_ev:
                note = (
                    f"proposed shift {shift:+.2f} eV exceeds ±{max_shift_ev:g} eV "
                    "— beyond plausible mono drift (E0 fit likely latched onto "
                    "a glitch); left unshifted."
                )
                shift = 0.0
                refused = True
        out.append({
            "energy": energy + shift,
            "mu": mu,
            "e0_before": None if e0 is None else round(e0, 4),
            "shift_applied": round(float(shift), 4),
            "e0_after": None if e0 is None else round(e0 + shift, 4),
            "refused": refused,
            "note": note,
            "target_e0": round(target, 4),
            "target_source": target_source,
        })
    return out


def difference_spectrum(energy_a, mu_a, energy_b, mu_b, align=True,
                        max_shift_ev=MAX_ALIGN_SHIFT_EV):
    """A − B on a common interpolated energy grid, optionally E0-aligned first.

    With ``align`` (the default), both spectra go through
    :func:`align_spectra` (target = A's E0) before interpolation, so the
    difference reflects spectral shape rather than a calibration offset —
    pass ``align=False`` to difference the raw axes. The grid is A's energy
    points restricted to the overlap region; B is interpolated onto it.

    Returns ``{energy, a, b, difference, aligned, alignment, stats}`` where
    ``stats`` carries ``max_abs_delta``, ``energy_of_max_abs_delta_ev``,
    ``rms_delta``, ``n_points`` and ``energy_range_ev``. Raises ValueError
    when the spectra share too little energy overlap.
    """
    ea = np.asarray(energy_a, dtype=float)
    ma = np.asarray(mu_a, dtype=float)
    eb = np.asarray(energy_b, dtype=float)
    mb = np.asarray(mu_b, dtype=float)

    alignment = None
    if align:
        records = align_spectra([(ea, ma), (eb, mb)], max_shift_ev=max_shift_ev)
        ea, eb = records[0]["energy"], records[1]["energy"]
        alignment = [
            {k: r[k] for k in ("e0_before", "shift_applied", "e0_after",
                               "refused", "note")}
            for r in records
        ]

    lo = max(float(ea.min()), float(eb.min()))
    hi = min(float(ea.max()), float(eb.max()))
    grid = ea[(ea >= lo) & (ea <= hi)]
    if grid.size < 5:
        raise ValueError(
            "Spectra share too little energy overlap for a difference "
            f"(overlap [{lo:.2f}, {hi:.2f}] eV holds {grid.size} points)."
        )
    a = np.interp(grid, ea, ma)
    b = np.interp(grid, eb, mb)
    diff = a - b
    i_max = int(np.argmax(np.abs(diff)))
    stats = {
        "max_abs_delta": round(float(np.abs(diff[i_max])), 6),
        "energy_of_max_abs_delta_ev": round(float(grid[i_max]), 4),
        "rms_delta": round(float(np.sqrt(np.mean(np.square(diff)))), 6),
        "n_points": int(grid.size),
        "energy_range_ev": [round(lo, 4), round(hi, 4)],
    }
    return {
        "energy": grid,
        "a": a,
        "b": b,
        "difference": diff,
        "aligned": bool(align),
        "alignment": alignment,
        "stats": stats,
    }


def compare_to_references(axis, intensity, references: list[dict]) -> dict:
    """Non-negative linear-combination fit of a spectrum to reference spectra.

    ``references`` = list of ``{"name", "axis", "intensity"}`` (the legacy
    XRS key ``"loss"`` is accepted as an alias for ``"axis"``). All are
    interpolated onto the target axis, then fit with non-negative least
    squares; fractions are normalized to sum 1. Returns fractions + fit
    residual, or ``{"error": ...}`` on degenerate input.
    """
    from scipy.optimize import nnls

    axis = np.asarray(axis, dtype=float)
    intensity = np.asarray(intensity, dtype=float)
    ok = np.isfinite(axis) & np.isfinite(intensity)
    axis, intensity = axis[ok], intensity[ok]
    if len(references) < 1 or axis.size < 3:
        return {"error": "Need a spectrum and ≥1 reference."}
    cols, names = [], []
    for ref in references:
        raxis = ref.get("axis", ref.get("loss"))
        rl = np.asarray(raxis, dtype=float)
        ri = np.asarray(ref["intensity"], dtype=float)
        cols.append(np.interp(axis, rl, ri, left=np.nan, right=np.nan))
        names.append(ref.get("name", f"ref{len(names)}"))
    A = np.vstack(cols).T
    good = np.all(np.isfinite(A), axis=1) & np.isfinite(intensity)
    A, b = A[good], intensity[good]
    if A.shape[0] < A.shape[1] + 1:
        return {"error": "Too little overlap between spectrum and references."}
    coeffs, resid = nnls(A, b)
    total = float(coeffs.sum())
    fractions = (coeffs / total).tolist() if total > 0 else coeffs.tolist()
    ss_res = float(np.sum((A @ coeffs - b) ** 2))
    ss_tot = float(np.sum((b - b.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else None
    return {
        "components": [{"name": n, "fraction": round(f, 4), "raw_weight": round(float(c), 6)}
                       for n, f, c in zip(names, fractions, coeffs)],
        "fit_r2": round(r2, 4) if r2 is not None else None,
        "residual_norm": round(float(resid), 6),
        "n_points_used": int(A.shape[0]),
    }
