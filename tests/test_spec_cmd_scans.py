"""Renderer/parser tests for the multi-region scan CommandSpecs
(gscan, kscan, absenergy) and the mock-transport env overrides.

These commands were added for simpler XAS/EXAFS stations (BL4-1); the
tests also pin backward compatibility of the surfaces they touch
(default mock motor set, default counter priority).
"""
from __future__ import annotations

import importlib
import json

import pytest

from beamtimehero_cli.spec_control import spec_cmd


# ---------------------------------------------------------------------------
# gscan
# ---------------------------------------------------------------------------

def test_gscan_render_single_region():
    s = spec_cmd.render("gscan", ["mono", "6540", "6620", "5", "1"])
    assert s == "gscan mono 6540 6620 5 1"


def test_gscan_render_multi_region():
    s = spec_cmd.render(
        "gscan",
        ["mono", "6540", "6542", "1", "6550", "0.2", "6570", "1", "6620", "5", "1"],
    )
    assert s == "gscan mono 6540 6542 1 6550 0.2 6570 1 6620 5 1"


@pytest.mark.parametrize("args", [
    ["mono", "6540", "6620", "5"],                 # missing count time
    ["mono", "6540", "6620"],                      # too few args
    ["mono", "6540", "6620", "5", "6700", "1"],    # dangling region pair
])
def test_gscan_render_rejects_bad_arity(args):
    with pytest.raises(ValueError):
        spec_cmd.render("gscan", args)


def test_gscan_render_rejects_empty_region():
    # end < start with positive step -> no points
    with pytest.raises(ValueError):
        spec_cmd.render("gscan", ["mono", "6620", "6540", "5", "1"])


def test_gscan_render_rejects_zero_count_time():
    with pytest.raises(ValueError):
        spec_cmd.render("gscan", ["mono", "6540", "6620", "5", "0"])


def test_gscan_render_rejects_bad_motor():
    with pytest.raises(ValueError):
        spec_cmd.render("gscan", ["mono; sleep(1)", "6540", "6620", "5", "1"])


def test_gscan_parser_extracts_scan_number():
    parsed = spec_cmd._parse_gscan(
        "Scan #1042 complete. File=mock.01  motor=mono",
        ["mono", "6540", "6620", "5", "1"],
    )
    assert parsed["scan_number"] == 1042
    assert parsed["file_name"] == "mock.01"
    assert parsed["motor"] == "mono"
    assert parsed["end"] == 6620.0
    assert parsed["count_time"] == 1.0


def test_gscan_parser_multi_region_end():
    parsed = spec_cmd._parse_gscan(
        "Scan #7 complete. File=mock.01  motor=mono",
        ["mono", "7080", "7100", "5", "7300", "3", "0.5"],
    )
    assert parsed["end"] == 7300.0


# ---------------------------------------------------------------------------
# kscan
# ---------------------------------------------------------------------------

_KSCAN_OK = [
    "6738", "0.5", "1", "6746",
    "0.1", "1", "6756",
    "0.5", "1", "6760",
    "6749", "1.75", "0.05", "11.0", "1", "12", "2",
]


def test_kscan_render_matches_macro_example():
    s = spec_cmd.render("kscan", _KSCAN_OK)
    assert s == "kscan 6738 0.5 1 6746 0.1 1 6756 0.5 1 6760 6749 1.75 0.05 11 1 12 2"


def test_kscan_render_minimum_form():
    # one eV region + 7 k parameters = 11 args
    s = spec_cmd.render(
        "kscan",
        ["6738", "0.5", "1", "6760", "6749", "1.75", "0.05", "11", "1", "12", "2"],
    )
    assert s.startswith("kscan 6738")


@pytest.mark.parametrize("args", [
    _KSCAN_OK[:-1],                       # (argc-8) % 3 != 0
    ["6738", "0.5", "1", "6760"],         # far too few
    [],                                   # empty
])
def test_kscan_render_rejects_bad_arity(args):
    with pytest.raises(ValueError):
        spec_cmd.render("kscan", args)


def test_kscan_render_rejects_inverted_k_region():
    bad = list(_KSCAN_OK)
    bad[-6], bad[-4] = "11.0", "1.75"     # k1 > k2
    with pytest.raises(ValueError):
        spec_cmd.render("kscan", bad)


def test_kscan_parser():
    parsed = spec_cmd._parse_kscan(
        "Scan #7 complete. File=mock.01  motor=mono", _KSCAN_OK
    )
    assert parsed["scan_number"] == 7
    assert parsed["motor"] == "mono"
    assert parsed["e0_ev"] == 6749.0
    assert parsed["k_end"] == 11.0


# ---------------------------------------------------------------------------
# absenergy
# ---------------------------------------------------------------------------

def test_absenergy_render():
    assert spec_cmd.render("absenergy", ["7112"]) == "absenergy 7112.0"


def test_absenergy_parser_success():
    parsed = spec_cmd._parse_absenergy(
        "absenergy complete. absev=7112.03 error=0.01 (successful_absenergy=1)",
        ["7112"],
    )
    assert parsed["target_ev"] == 7112.0
    assert parsed["achieved_ev"] == pytest.approx(7112.03)
    assert parsed["converged"] is True


def test_absenergy_parser_failure():
    parsed = spec_cmd._parse_absenergy("absenergy failed after 15 tries", ["7112"])
    assert parsed["converged"] is False


# ---------------------------------------------------------------------------
# Registration + backward compatibility
# ---------------------------------------------------------------------------

def test_new_commands_registered_as_actions():
    known = spec_cmd.known_commands()
    for name in ("gscan", "kscan", "absenergy"):
        assert name in known["action"]
        assert spec_cmd.command_kind(name) == "action"


def test_mock_motor_defaults_unchanged():
    """The BL15-2 default mock motor set must survive the env-override hook."""
    from beamtimehero_cli.spec_control import transport

    positions = transport._mock_default_positions()
    for motor in ("m1vert", "energy", "emiss", "Sx", "Sy", "Sz", "gap", "mono"):
        assert motor in positions
    assert positions["energy"] == 7100.0


def test_mock_motor_env_override(monkeypatch):
    from beamtimehero_cli.spec_control import transport

    monkeypatch.setenv(
        "SPEC_MOCK_MOTORS", json.dumps({"mono": 7100.0, "Sx": 1.0, "Sz": 2.0})
    )
    positions = transport._mock_default_positions()
    assert set(positions) == {"mono", "Sx", "Sz"}


def test_mock_motor_env_override_malformed_keeps_defaults(monkeypatch):
    from beamtimehero_cli.spec_control import transport

    monkeypatch.setenv("SPEC_MOCK_MOTORS", "{not json")
    positions = transport._mock_default_positions()
    assert "m1vert" in positions and "gap" in positions


def test_mock_inject_gscan_and_absenergy():
    from beamtimehero_cli.spec_control import transport

    out = transport._MockScreen.inject("gscan mono 6540 6620 5 1")
    assert "complete" in out.lower()
    out = transport._MockScreen.inject("absenergy 7112")
    assert "absev=7112" in out
    assert transport._MockScreen._positions["mono"] == 7112.0


def test_counter_priority_default_unchanged():
    """With no priority supplied, pick_active_counter keeps historical behavior."""
    import pandas as pd

    from beamtimehero_cli.science.reduce import counters

    df = pd.DataFrame({"vortDT": [1.0, 5.0], "I1": [2.0, 2.1]})
    counter, _reason = counters.pick_active_counter(df)
    assert counter == "vortDT"


def test_counter_priority_override_is_honored():
    """The science function is pure: the override arrives as an argument."""
    import pandas as pd

    from beamtimehero_cli.science.reduce import counters

    df = pd.DataFrame({"vortDT": [1.0, 5.0], "I1": [2.0, 2.1]})
    counter, reason = counters.pick_active_counter(df, priority=("I1", "I2"))
    assert counter == "I1"
    assert "override" in reason


def test_counter_priority_read_from_env_by_config(monkeypatch):
    """config owns the env read; science/ never touches os.environ."""
    from beamtimehero_cli import config as bl_config

    monkeypatch.delenv("BTH_ACTIVE_COUNTER_PRIORITY", raising=False)
    assert bl_config.active_counter_priority() == ()

    monkeypatch.setenv("BTH_ACTIVE_COUNTER_PRIORITY", "I1, I2 ,")
    assert bl_config.active_counter_priority() == ("I1", "I2")
