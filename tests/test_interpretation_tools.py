"""Tests for the CAT-10 interpretation TOOL layer (handlers via execute_tool).

Complements ``test_interpretation.py`` (which tests the pure package). Here the
scan loaders are monkeypatched so the tools see a synthetic Fe K-edge spectrum
(erf edge + Gaussian pre-edge + Gaussian white line — the same known-ground-
truth model as the package tests), and every call goes through the real
``execute_tool`` dispatch on the ``spec-file`` tree.

Covers the 7 new atomic descriptor tools (each returns its single result) and
the capstones' precomputed-``descriptors`` passthrough: feeding
``extract_xas_descriptors``' output back into a capstone must reproduce the
recompute-path verdict while skipping the pipeline (no plot).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
from scipy.special import erf

# Ground-truth Fe K-edge model (mirrors test_interpretation.py).
E = np.arange(7090.0, 7220.0, 0.25)
EDGE_C, PRE_C, PRE_S, PRE_A, WL_C = 7120.0, 7113.2, 0.6, 0.08, 7124.0


def _fe_over_i0(shift: float = 0.0) -> np.ndarray:
    return (0.5 * (1 + erf((E - (EDGE_C + shift)) / 2.0))
            + PRE_A * np.exp(-0.5 * ((E - (PRE_C + shift)) / PRE_S) ** 2)
            + 0.9 * np.exp(-0.5 * ((E - (WL_C + shift)) / 2.0) ** 2))


def _fe_df(seed: int = 0, shift: float = 0.0) -> pd.DataFrame:
    """A scan DataFrame: flat I0 + a vortDT2 fluorescence channel (counts)."""
    rng = np.random.RandomState(seed)
    i0 = np.full(len(E), 1.0e5)
    df = pd.DataFrame(
        {"I0": i0, "vortDT2": _fe_over_i0(shift) * i0 + rng.normal(0, 40, len(E))},
        index=E,
    )
    df.attrs["count_time"] = 1.0
    df.attrs["motor_positions"] = {}
    return df


@pytest.fixture
def fe_scans(monkeypatch, tmp_path):
    """Patch loaders so the tools read scans 1..6 of a synthetic Fe K-edge file.

    ``BL_SCAN_DIR`` -> tmp_path so the calibration store finds no record (the
    axis is then assumed foil-calibrated — deterministic across calls).
    """
    from beamtimehero_cli import config as bl_config
    from beamtimehero_cli.spec_data import scans, local_data

    monkeypatch.setattr(bl_config, "BL_SCAN_DIR", str(tmp_path))
    dfs = {sn: _fe_df(seed=sn) for sn in range(1, 7)}

    monkeypatch.setattr(scans, "read_processed_scan",
                        lambda fn, sn: dfs.get(int(sn)))
    monkeypatch.setattr(local_data, "get_scan_numbers_for_file",
                        lambda fn: sorted(dfs))
    monkeypatch.setattr(scans, "get_most_recent_file", lambda: "fe_test")
    monkeypatch.setattr(local_data, "get_most_recent_file", lambda: "fe_test")
    return "fe_test"


def _run(name, payload, tree=("spec-file",)):
    from beamtimehero_cli.tool_catalog import execute_tool
    text, images = execute_tool(tree, name, payload)
    return json.loads(text), images


# ---------------------------------------------------------------------------
# The 7 atomic tools — each returns its single result
# ---------------------------------------------------------------------------

def test_identify_edge(fe_scans):
    out, imgs = _run("identify_edge", {"file_name": fe_scans})
    assert "error" not in out
    assert out["edge"]["element"] == "Fe" and out["edge"]["edge"] == "K"
    assert out["edge"]["family"] == "3d_K"
    assert out["energy_window_ev"][0] == pytest.approx(E.min(), abs=0.5)
    assert imgs == []


def test_find_edge_e0(fe_scans):
    out, imgs = _run("find_edge_e0", {"file_name": fe_scans})
    assert out["e0"]["e0_ev"] == pytest.approx(EDGE_C, abs=1.5)
    assert out["e0"]["e0_unc_ev"] > 0
    assert imgs == []


def test_normalize_xas_intensity(fe_scans):
    out, _ = _run("normalize_xas_intensity", {"file_name": fe_scans})
    assert out["normalization"] == "area"
    assert out["provenance"]["method"] == "area" and out["provenance"]["applied"]
    # mback path still resolves (Fe/K) and applies
    mb, _ = _run("normalize_xas_intensity",
                 {"file_name": fe_scans, "normalization": "mback"})
    assert mb["provenance"]["method"] == "mback"


def test_fit_xas_pre_edge(fe_scans):
    out, _ = _run("fit_xas_pre_edge", {"file_name": fe_scans})
    pe = out["pre_edge"]
    assert pe["fit_ok"]
    assert pe["centroid_ev"] == pytest.approx(PRE_C, abs=0.2)
    # Fe carries a core-hole width -> the re-broadened variant is present
    assert out["pre_edge_rebroadened"] is not None
    assert out["pre_edge_rebroadened"]["provenance"]["calibration_domain"] == \
        "herfd_rebroadened"


def test_fit_xas_white_line(fe_scans):
    out, _ = _run("fit_xas_white_line", {"file_name": fe_scans})
    wl = out["white_line"]
    assert wl["fit_ok"]
    assert wl["white_line_energy_ev"] == pytest.approx(WL_C, abs=0.3)
    assert wl["white_line_height"] > 0.4


def test_assess_xas_quality(fe_scans):
    out, imgs = _run("assess_xas_quality", {"file_name": fe_scans})
    assert not out["saturation"]["saturated"]
    # no assume_dilute -> self-absorption risk unknown, flagged
    assert out["self_absorption"]["risk"] == "unknown"
    assert "self_absorption_risk" in out["flags"]
    assert imgs == []
    # asserting dilute lifts the risk flag
    dil, _ = _run("assess_xas_quality",
                  {"file_name": fe_scans, "assume_dilute": True})
    assert "self_absorption_risk" not in dil["flags"]


def test_detect_per_scan_drift(fe_scans):
    out, _ = _run("detect_per_scan_drift", {"file_name": fe_scans})
    # 6 stable reps -> structure present, no monotonic drift
    assert "drift_detected" in out and "per_metric" in out
    assert "e0_ev" in out["per_metric"]
    assert out["drift_detected"] is False


# ---------------------------------------------------------------------------
# Capstone de-duplication: precomputed `descriptors` passthrough
# ---------------------------------------------------------------------------

def test_capstone_accepts_precomputed_descriptors(fe_scans):
    # 1. the source-of-truth descriptor bundle
    desc, desc_imgs = _run("extract_xas_descriptors", {"file_name": fe_scans})
    assert "error" not in desc and desc_imgs  # extract carries the plot

    # 2. recompute path (no descriptors arg) — the backward-compatible default
    recompute, recompute_imgs = _run("summarize_sample_chemistry",
                                     {"file_name": fe_scans})
    assert recompute_imgs  # annotated plot on the recompute path

    # 3. passthrough path — feed extract's output back in
    passthrough, pass_imgs = _run("summarize_sample_chemistry",
                                  {"descriptors": desc})

    # same verdict, no recomputation-driven plot (arrays not carried in JSON)
    assert pass_imgs == []
    assert passthrough["oxidation_state"]["estimate"] == \
        recompute["oxidation_state"]["estimate"]
    assert passthrough["coordination_geometry"]["estimate"] == \
        recompute["coordination_geometry"]["estimate"]
    assert passthrough["beam_damage"]["drift_detected"] == \
        recompute["beam_damage"]["drift_detected"]
    assert passthrough["narration"] == recompute["narration"]


def test_oxidation_state_descriptors_passthrough_matches(fe_scans):
    desc, _ = _run("extract_xas_descriptors", {"file_name": fe_scans})
    recompute, _ = _run("interpret_oxidation_state", {"file_name": fe_scans})
    passthrough, _ = _run("interpret_oxidation_state", {"descriptors": desc})
    assert passthrough["estimate"] == recompute["estimate"]
    assert passthrough["confidence"] == recompute["confidence"]
    assert passthrough["narration"] == recompute["narration"]
    # file/scan provenance is peeled back off the bundle
    assert passthrough["file_name"] == desc["file_name"]
