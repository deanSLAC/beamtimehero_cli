"""Tests for the scientific-interpretation package (synthetic spectra).

Follows the repo convention: pure-math tests on crafted arrays, no
backend or data-file dependency. The synthetic model is
erf edge + Gaussian pre-edge + Gaussian white line, so every descriptor
has a known ground truth.
"""
import json

import numpy as np
import pytest
from scipy.special import erf

from beamtimehero_cli.interpretation import calibration_store, edges, quality
from beamtimehero_cli.interpretation import descriptors as D
from beamtimehero_cli.interpretation import interpret as I
from beamtimehero_cli.interpretation import normalize as N

E = np.arange(7090.0, 7220.0, 0.25)
EDGE_C, PRE_C, PRE_A, PRE_S, WL_C = 7120.0, 7113.2, 0.08, 0.6, 7124.0
TRUE_PRE_AREA = PRE_A * PRE_S * np.sqrt(2 * np.pi)
FE = {"element": "Fe", "edge": "K", "family": "3d_K",
      "tabulated_energy_ev": 7112.0, "core_hole_width_ev": 1.25}


def fe_spectrum(shift=0.0, e=E, pre_a=PRE_A):
    return (0.5 * (1 + erf((e - (EDGE_C + shift)) / 2.0))
            + pre_a * np.exp(-0.5 * ((e - (PRE_C + shift)) / PRE_S) ** 2)
            + 0.9 * np.exp(-0.5 * ((e - (WL_C + shift)) / 2.0) ** 2))


FE_CALIB = {
    "calibrated": True, "offset_ev": 0.0, "element": "Fe", "edge": "K",
    "assigned_reference_ev": 7112.0, "measured_e0_unc_ev": 0.05,
}

# What current_calibration() returns when no record exists: the mono is
# assumed foil-calibrated (offset 0, ~0.2 eV systematic).
ASSUMED_CALIB = {
    "calibrated": True, "assumed": True, "offset_ev": 0.0,
    "measured_e0_unc_ev": 0.2, "reason": "assumed foil-calibrated",
}


# ---------------------------------------------------------------------------
# edges.py — xraydb offline
# ---------------------------------------------------------------------------

def test_xraydb_offline_lookups():
    info = edges.get_edge_info("Fe", "K")
    assert info["tabulated_energy_ev"] == pytest.approx(7112.0, abs=1.0)
    assert info["core_hole_width_ev"] == pytest.approx(1.25, abs=0.1)
    assert info["family"] == "3d_K"
    assert edges.classify_edge_family("Ce", "L3") == "ln_L3"
    assert edges.classify_edge_family("Pt", "L3") == "5d_L3"
    assert edges.classify_edge_family("U", "M4") == "an_M"
    # 4d/5d transition-metal K-edges are now in scope
    assert edges.classify_edge_family("Ru", "K") == "4d_K"
    assert edges.classify_edge_family("Zr", "K") == "4d_K"
    assert edges.classify_edge_family("Au", "K") == "5d_K"
    # Ca (Z=20) sits just below the 3d block — genuinely out of scope
    assert edges.classify_edge_family("Ca", "K") == "other"


def test_suggest_edge_from_window():
    s = edges.suggest_edge(7090, 7220)
    assert s["found"] and s["best"]["element"] == "Fe" and s["best"]["edge"] == "K"
    assert not edges.suggest_edge(1000, 1050)["found"]


# ---------------------------------------------------------------------------
# descriptors.py
# ---------------------------------------------------------------------------

def test_e0_and_descriptor_recovery():
    desc, _ = D.extract_descriptors(E, fe_spectrum(), edge_info=FE)
    # erf edge: derivative max at the edge center, modulated by wl slope
    assert desc["e0"]["e0_ev"] == pytest.approx(EDGE_C, abs=1.0)
    pe = desc["pre_edge"]
    assert pe["fit_ok"]
    assert pe["centroid_ev"] == pytest.approx(PRE_C, abs=0.05)
    assert pe["total_area"] == pytest.approx(TRUE_PRE_AREA, rel=0.05)
    wl = desc["white_line"]
    assert wl["white_line_energy_ev"] == pytest.approx(WL_C, abs=0.1)
    assert wl["white_line_height"] > 0.5


def test_centroid_recovery_with_noise():
    rng = np.random.default_rng(7)
    mu = fe_spectrum() + rng.normal(0, 0.01, len(E))
    desc, _ = D.extract_descriptors(E, mu, edge_info=FE)
    assert desc["pre_edge"]["centroid_ev"] == pytest.approx(PRE_C, abs=0.1)


def test_shifted_edge_moves_centroid_by_shift():
    d2, _ = D.extract_descriptors(E, fe_spectrum(0.0), edge_info=FE)
    d3, _ = D.extract_descriptors(E, fe_spectrum(1.4), edge_info=FE)
    delta = d3["pre_edge"]["centroid_ev"] - d2["pre_edge"]["centroid_ev"]
    assert delta == pytest.approx(1.4, abs=0.1)


def test_rebroaden_widens_and_conserves_area():
    mu = fe_spectrum()
    broadened = D.rebroaden(E, mu, 1.25)
    desc_sharp, _ = D.extract_descriptors(E, mu, edge_info=FE)
    rb = desc_sharp["pre_edge_rebroadened"]
    assert rb is not None and rb["fit_ok"]
    assert rb["provenance"]["calibration_domain"] == "herfd_rebroadened"
    # centroid survives re-broadening; area approximately conserved (the
    # broadened peak/baseline separation is genuinely degenerate, so the
    # area systematic is larger than for the sharp fit)
    assert rb["centroid_ev"] == pytest.approx(PRE_C, abs=0.35)
    assert rb["total_area"] == pytest.approx(TRUE_PRE_AREA, rel=0.2)
    # broadened peak is wider than the sharp one
    sharp_fwhm = desc_sharp["pre_edge"]["components"][0]["fwhm_ev"]
    e_sel = (E > 7110) & (E < 7116)
    assert np.max(broadened[e_sel]) < np.max(mu[e_sel])
    assert sharp_fwhm < 2.0


def test_glitch_masking():
    mu = fe_spectrum().copy()
    mu[100] += 0.8  # single-point mono glitch in the pre-edge region
    mask = quality.detect_glitches(E, mu)
    assert mask[100]
    desc, _ = D.extract_descriptors(E, mu, edge_info=FE)
    assert "glitch_masked" in desc["flags"]
    assert desc["pre_edge"]["centroid_ev"] == pytest.approx(PRE_C, abs=0.1)


def test_saturation_detection():
    mu = fe_spectrum().copy()
    mu = np.minimum(mu, 1.2)  # clipped white line
    assert quality.detect_saturation(mu)["saturated"]
    assert not quality.detect_saturation(fe_spectrum())["saturated"]


def test_area_normalization():
    mu = 2.5 * fe_spectrum()  # arbitrary scale
    mu_n, prov = N.area_normalize(E, mu, EDGE_C)
    assert prov["applied"]
    sel = (E >= EDGE_C + 20) & (E <= EDGE_C + 100)
    mean = np.trapezoid(mu_n[sel], E[sel]) / (E[sel][-1] - E[sel][0])
    assert mean == pytest.approx(1.0, rel=1e-6)
    # short scan: refuses rather than silently mis-normalizing
    e_short = E[E < EDGE_C + 25]
    _, prov_short = N.area_normalize(e_short, fe_spectrum(e=e_short), EDGE_C)
    assert not prov_short["applied"]


def test_mback_normalization():
    mu = 2.5 * fe_spectrum()  # arbitrary scale MBACK must absorb
    mu_n, prov = N.mback_normalize(E, mu, EDGE_C, "Fe", "K")
    assert prov["applied"] and prov["method"] == "mback"
    assert np.all(np.isfinite(mu_n))
    # unit-edge-step scale: pre-edge ~0, post-edge ~1 (same scale as area)
    pre = mu_n[E < EDGE_C - 25]
    post = mu_n[(E > EDGE_C + 35) & (E < EDGE_C + 90)]
    assert abs(float(pre.mean())) < 0.2
    assert 0.6 < float(post.mean()) < 1.4
    # the white line (a real spectral feature) survives the background fit
    wl = mu_n[(E > WL_C - 2) & (E < WL_C + 2)].max()
    assert wl > float(post.mean())
    # aligns the tabulated Fe edge (7112 eV) onto the observed E0 (7120)
    assert prov["edge_shift_ev"] == pytest.approx(EDGE_C - 7112.0, abs=1.5)


def test_mback_degrades_gracefully():
    mu = fe_spectrum()
    # no element/edge -> unchanged spectrum + reason, never raises
    same, prov = N.mback_normalize(E, mu, EDGE_C, None, "K")
    assert not prov["applied"] and "reason" in prov
    assert np.array_equal(same, mu)
    # short scan with no post-edge region -> refuses
    e_short = E[E < EDGE_C + 20]
    _, prov_short = N.mback_normalize(e_short, fe_spectrum(e=e_short), EDGE_C, "Fe", "K")
    assert not prov_short["applied"]


def test_mback_through_extract_descriptors():
    desc, _ = D.extract_descriptors(E, fe_spectrum(), edge_info=FE, normalization="mback")
    assert desc["provenance"]["normalization"]["method"] == "mback"
    assert desc["provenance"]["normalization"]["applied"]
    assert "mback_normalization_unavailable" not in desc["flags"]
    # descriptors still recovered on the MBACK-normalized spectrum
    assert desc["pre_edge"]["fit_ok"]
    assert desc["e0"]["e0_ev"] == pytest.approx(EDGE_C, abs=1.0)
    json.dumps(desc, default=str)
    # coordination verdict flags the non-area normalization (HERFD intensity)
    v = I.interpret_coordination_geometry(desc, FE_CALIB)
    assert any("not area" in c for c in v["caveats"])


def test_per_scan_drift_detection():
    rng = np.random.default_rng(3)
    drifting = np.array([fe_spectrum(shift=-0.06 * i) + rng.normal(0, 0.004, len(E))
                         for i in range(10)])
    stable = np.array([fe_spectrum() + rng.normal(0, 0.004, len(E))
                       for _ in range(10)])
    d_drift, _ = D.extract_descriptors(E, drifting.mean(axis=0), reps=drifting,
                                       edge_info=FE)
    d_stable, _ = D.extract_descriptors(E, stable.mean(axis=0), reps=stable,
                                        edge_info=FE)
    trends = d_drift["per_scan_trends"]
    assert trends["drift_detected"]
    assert "e0_ev" in trends["drifting_metrics"]
    assert trends["per_metric"]["e0_ev"]["theil_slope_per_scan"] < 0
    assert not d_stable["per_scan_trends"]["drift_detected"]


# ---------------------------------------------------------------------------
# calibration_store.py
# ---------------------------------------------------------------------------

def test_calibration_record_roundtrip(tmp_path, monkeypatch):
    from beamtimehero_cli import config as bl_config
    monkeypatch.setattr(bl_config, "BL_SCAN_DIR", str(tmp_path))
    # No record: the axis is assumed foil-calibrated (offset 0), not refused
    cc = calibration_store.current_calibration()
    assert cc["calibrated"] and cc["assumed"] and cc["offset_ev"] == 0.0
    calibration_store.record_calibration(
        element="Fe", edge="K", measured_e0_ev=7111.4, measured_e0_unc_ev=0.06,
        assigned_reference_ev=7112.0, reference_source="test", file_name="foil.dat",
        scan_numbers=[1, 2], e0_definition=D.E0_DEFINITION,
    )
    cal = calibration_store.current_calibration()
    # an explicit record takes precedence over the assume-calibrated default
    assert cal["calibrated"] and not cal.get("assumed")
    assert cal["offset_ev"] == pytest.approx(0.6)
    calibration_store.record_calibration(
        element="Fe", edge="K", measured_e0_ev=7111.2, measured_e0_unc_ev=0.06,
        assigned_reference_ev=7112.0, reference_source="test", file_name="foil.dat",
        scan_numbers=[9], e0_definition=D.E0_DEFINITION,
    )
    cal = calibration_store.current_calibration()
    assert cal["n_records"] == 2
    assert cal["drift"]["offset_span_ev"] == pytest.approx(0.2, abs=1e-9)


# ---------------------------------------------------------------------------
# interpret.py — rigor gates and verdicts
# ---------------------------------------------------------------------------

def test_assumed_calibration_yields_estimate_not_refusal():
    # No explicit calibration record: the axis is assumed foil-calibrated,
    # so a position-based oxidation state is estimated, not refused.
    desc, _ = D.extract_descriptors(E, fe_spectrum(), edge_info=FE)
    v = I.interpret_oxidation_state(desc, ASSUMED_CALIB)
    assert v["confidence"] != "refused"
    assert v.get("refused_absolute") is not True
    assert v["estimate"] is not None
    assert v["narration"]


def test_ru_k_edge_classified_and_interpreted():
    # A 4d transition-metal K-edge (Ru, Z=44) is now in scope and must not
    # be refused as an unsupported family.
    ru = edges.get_edge_info("Ru", "K")
    assert ru["family"] == "4d_K"
    e0_tab = ru["tabulated_energy_ev"]
    e = np.arange(e0_tab - 30.0, e0_tab + 100.0, 0.25)
    edge_c = e0_tab + 3.0  # sample edge a few eV above tabulated (oxidized)
    mu = (0.5 * (1 + erf((e - edge_c) / 2.0))
          + 0.05 * np.exp(-0.5 * ((e - (e0_tab - 8.0)) / 0.7) ** 2)  # 1s->4d pre-edge
          + 0.9 * np.exp(-0.5 * ((e - (edge_c + 6.0)) / 2.5) ** 2))  # white line
    desc, _ = D.extract_descriptors(e, mu, edge_info=ru)
    v = I.interpret_oxidation_state(desc, ASSUMED_CALIB)
    assert v["family"] == "4d_K"
    assert v["confidence"] != "refused"
    assert v["estimate"] is not None
    # anchored on the tabulated edge under the assume-calibrated model
    assert any("tabulated" in c.lower() for c in v["caveats"])
    assert v["narration"]
    json.dumps(v, default=str)


def test_calibrated_fe_oxidation_state_moves_with_shift():
    d2, _ = D.extract_descriptors(E, fe_spectrum(0.0), edge_info=FE)
    d3, _ = D.extract_descriptors(E, fe_spectrum(1.4), edge_info=FE)
    # calibrate so the Fe2-like centroid lands on the Wilke Fe2+ reference
    offset = 7112.1 - d2["pre_edge_rebroadened"]["centroid_ev"]
    calib = dict(FE_CALIB, offset_ev=offset)
    v2 = I.interpret_oxidation_state(d2, calib)
    v3 = I.interpret_oxidation_state(d3, calib)
    assert v2["estimate"] == pytest.approx(2.0, abs=0.15)
    assert v3["estimate"] == pytest.approx(3.0, abs=0.25)
    assert v2["confidence"] in ("medium", "low")
    assert v2["narration"]  # narration built from real numbers


def test_coordination_geometry_intensity_brackets():
    strong, _ = D.extract_descriptors(E, fe_spectrum(pre_a=0.14), edge_info=FE)
    weak, _ = D.extract_descriptors(E, fe_spectrum(pre_a=0.03), edge_info=FE)
    v_strong = I.interpret_coordination_geometry(strong, FE_CALIB)
    v_weak = I.interpret_coordination_geometry(weak, FE_CALIB)
    assert "non-centrosymmetric" in v_strong["estimate"]
    assert "centrosymmetric (octahedral" in v_weak["estimate"]
    # self-absorption unknown -> confidence degraded from medium
    assert v_strong["confidence"] == "low"
    dilute, _ = D.extract_descriptors(E, fe_spectrum(pre_a=0.14), edge_info=FE,
                                      assume_dilute=True)
    assert I.interpret_coordination_geometry(dilute, FE_CALIB)["confidence"] == "medium"


def test_ce_l3_doublet_detected_without_calibration():
    e = np.arange(5680.0, 5800.0, 0.25)
    ce = edges.get_edge_info("Ce", "L3")
    # Ce(IV)-like: 4f1L + 4f0 doublet on the L3 edge
    mu = (0.5 * (1 + erf((e - 5727.0) / 2.5))
          + 0.8 * np.exp(-0.5 * ((e - 5729.0) / 1.5) ** 2)
          + 0.7 * np.exp(-0.5 * ((e - 5737.0) / 1.8) ** 2))
    desc, _ = D.extract_descriptors(e, mu, edge_info=ce, white_line_components=3)
    v = I.interpret_oxidation_state(desc, {"calibrated": False})
    # shape-based: works uncalibrated, flags semi-quantitative nature
    assert v["estimate"] is not None and v["estimate"] > 3.2
    assert "doublet" in v["narration"] or "final-state" in v["narration"]
    assert any("LCF" in c for c in v["caveats"])


def test_u_m4_satellites_indicate_u6():
    e = np.arange(3700.0, 3765.0, 0.1)
    u = edges.get_edge_info("U", "M4")
    mu = (0.2 * (1 + erf((e - 3728.0) / 2.0))
          + 1.0 * np.exp(-0.5 * ((e - 3727.7) / 0.7) ** 2)
          + 0.25 * np.exp(-0.5 * ((e - 3729.6) / 0.7) ** 2)
          + 0.18 * np.exp(-0.5 * ((e - 3733.4) / 0.9) ** 2))
    desc, _ = D.extract_descriptors(e, mu, edge_info=u, white_line_components=3)
    v = I.interpret_oxidation_state(desc, {"calibrated": False})
    assert v["estimate"] == 6.0
    assert v["confidence"] == "medium"


def test_summarize_chemistry_flags_photoreduction():
    rng = np.random.default_rng(11)
    reps = np.array([fe_spectrum(shift=-0.06 * i) + rng.normal(0, 0.004, len(E))
                     for i in range(10)])
    desc, _ = D.extract_descriptors(E, reps.mean(axis=0), reps=reps, edge_info=FE)
    s = I.summarize_chemistry(desc, ASSUMED_CALIB)
    assert s["beam_damage"]["drift_detected"]
    assert "reduction" in s["beam_damage"]["direction"]
    assert "photoreduction" in s["narration"]
    json.dumps(s, default=str)  # whole verdict must be JSON-serializable


def test_output_contract_and_provenance():
    desc, _ = D.extract_descriptors(E, fe_spectrum(), edge_info=FE)
    v = I.interpret_oxidation_state(desc, FE_CALIB)
    for key in ("estimate", "range", "confidence", "basis", "descriptors_used",
                "calibration_context", "flags", "provenance", "caveats", "narration"):
        assert key in v
    prov = desc["provenance"]
    assert prov["normalization"]["method"] == "area"
    assert "herfd" in prov["herfd_caveat"].lower() or "RIXS" in prov["herfd_caveat"]
    assert desc["pre_edge"]["provenance"]["baseline_model"] == "step(atan) + linear"
    json.dumps(desc, default=str)
