"""Pinned values for every scientific default in ``science/*/policy.py``.

These are not correctness tests — nothing here asserts the physics is right.
They assert the numbers are what someone *chose*, so that changing one is a
deliberate act rather than a silent one.

The gap this closes: the policy modules centralize the scientific defaults, so
a one-token edit in one file changes what every tool computes. Before this
file, all of those edits left the suite green — a contributor could widen the
pre-edge window by 50%, empty the multi-component family list, or triple the
k-weight and get no signal at all.

**If a test here fails and you meant it:** update the expected value in the
same commit as the change. The diff on this file is then the record of which
physics defaults moved and when, which is exactly what a reviewer wants to see.

The last two tests are the important ones — they check that the constants are
actually *wired*, in both directions:

  * the science functions take their defaults from policy, so a scientist
    calling them directly gets the same behaviour as the CLI, and
  * the agent-facing JSON schema takes its defaults from policy, so the tool
    description cannot drift from what the tool does.
"""
from __future__ import annotations

import inspect

import pytest

from beamtimehero_cli.science.exafs import policy as exafs_policy
from beamtimehero_cli.science.xas import policy as xas_policy
from beamtimehero_cli.science.xrs import policy as xrs_policy
from beamtimehero_cli.tool_catalog import TOOL_DEFINITIONS


# --------------------------------------------------------------------------
# XAS
# --------------------------------------------------------------------------

def test_xas_fit_windows():
    """Wilke-style pre-edge window and the white-line window, relative to E0."""
    assert xas_policy.PRE_EDGE_WINDOW_REL == (-20.0, -5.0)
    assert xas_policy.WHITE_LINE_WINDOW_REL == (-10.0, 40.0)


def test_xas_multi_component_families():
    """Which edge families get a multi-peak white line, and how many peaks."""
    assert xas_policy.MULTI_COMPONENT_FAMILIES == ("ln_L3", "an_L3", "an_M")
    assert xas_policy.MULTI_COMPONENT_COUNT == 3
    assert xas_policy.SINGLE_COMPONENT_COUNT == 1
    # the decision function, not just the constants
    assert xas_policy.white_line_components_for("ln_L3") == 3
    assert xas_policy.white_line_components_for("an_M") == 3
    assert xas_policy.white_line_components_for("3d_K") == 1
    assert xas_policy.white_line_components_for(None) == 1


def test_xas_data_adequacy_minimums():
    """Descriptor fits need more points than a reference spectrum does."""
    assert xas_policy.MIN_OVERLAPPING_POINTS == 20
    assert xas_policy.MIN_REFERENCE_POINTS == 10
    assert xas_policy.MIN_REFERENCE_POINTS < xas_policy.MIN_OVERLAPPING_POINTS

    xas_policy.check_overlap(20)                      # at the limit: fine
    with pytest.raises(ValueError, match="Too few overlapping"):
        xas_policy.check_overlap(19)

    xas_policy.check_reference_points(10, "ref.dat")  # at the limit: fine
    with pytest.raises(ValueError, match="too few overlapping"):
        xas_policy.check_reference_points(9, "ref.dat")


# --------------------------------------------------------------------------
# EXAFS
# --------------------------------------------------------------------------

def test_exafs_kspace_defaults():
    assert exafs_policy.DEFAULT_KWEIGHT == 2
    assert exafs_policy.DEFAULT_KMIN == 2.0
    assert exafs_policy.DEFAULT_KMAX is None      # None = full measured range
    assert exafs_policy.DEFAULT_DK == 1.0
    assert exafs_policy.DEFAULT_RBKG == 1.0


def test_exafs_point_minimum():
    assert exafs_policy.MIN_EXAFS_POINTS == 20
    exafs_policy.check_exafs_points(20)
    with pytest.raises(ValueError, match="for EXAFS extraction"):
        exafs_policy.check_exafs_points(19)


# --------------------------------------------------------------------------
# XRS
# --------------------------------------------------------------------------

def test_xrs_background_and_regime():
    assert xrs_policy.BACKGROUND_MODELS == ("constant", "linear", "pearson7")
    assert xrs_policy.DEFAULT_BACKGROUND_MODEL == "linear"
    assert xrs_policy.DEFAULT_BACKGROUND_MODEL in xrs_policy.BACKGROUND_MODELS
    assert xrs_policy.DIPOLE_REGIME_Q_MAX_INV_ANG == 3.0
    # the boundary is exclusive on the low side
    assert xrs_policy.q_regime(2.99) == xrs_policy.LOW_Q_LABEL
    assert xrs_policy.q_regime(3.0) == xrs_policy.HIGH_Q_LABEL


# --------------------------------------------------------------------------
# Wiring — the part that actually broke twice during review
# --------------------------------------------------------------------------

def _default_of(fn, param):
    return inspect.signature(fn).parameters[param].default


def test_science_signatures_read_from_policy():
    """A scientist calling the science function directly must get the policy
    default — not a literal that happens to agree with it today."""
    from beamtimehero_cli.science.exafs import background, fourier
    from beamtimehero_cli.science.xrs import reduce as xrs_reduce

    assert _default_of(fourier.xftf, "kweight") is exafs_policy.DEFAULT_KWEIGHT
    assert _default_of(fourier.xftf, "kmin") is exafs_policy.DEFAULT_KMIN
    assert _default_of(fourier.xftf, "kmax") is exafs_policy.DEFAULT_KMAX
    assert _default_of(fourier.xftf, "dk") is exafs_policy.DEFAULT_DK
    assert _default_of(fourier.ft_window, "dk") is exafs_policy.DEFAULT_DK
    assert _default_of(background.autobk_lite, "kweight") is exafs_policy.DEFAULT_KWEIGHT
    assert _default_of(background.autobk_lite, "rbkg") is exafs_policy.DEFAULT_RBKG
    assert (_default_of(xrs_reduce.subtract_compton_background, "model")
            is xrs_policy.DEFAULT_BACKGROUND_MODEL)


def _schema(tool_name):
    for d in TOOL_DEFINITIONS:
        if d["function"]["name"] == tool_name:
            return d["function"]["parameters"]["properties"]
    raise AssertionError(f"tool {tool_name!r} not in the catalog")


def test_agent_schema_reads_from_policy():
    """The JSON schema's defaults are what the CLI actually sends, so if they
    diverge from policy the tool lies to the agent about its own behaviour —
    and a policy edit silently does nothing on the CLI path."""
    ft = _schema("fourier_transform_chi")
    assert ft["kweight"]["default"] == exafs_policy.DEFAULT_KWEIGHT
    assert ft["kmin"]["default"] == exafs_policy.DEFAULT_KMIN
    assert ft["dk"]["default"] == exafs_policy.DEFAULT_DK

    chi = _schema("extract_chi")
    assert chi["rbkg"]["default"] == exafs_policy.DEFAULT_RBKG
    assert chi["kweight"]["default"] == exafs_policy.DEFAULT_KWEIGHT

    bg = _schema("subtract_compton_background")
    assert bg["model"]["default"] == xrs_policy.DEFAULT_BACKGROUND_MODEL
    assert bg["model"]["enum"] == list(xrs_policy.BACKGROUND_MODELS)


def test_every_policy_constant_is_pinned_here():
    """Catch a *new* policy constant that nobody pinned.

    Without this, adding a default to a policy module reintroduces exactly the
    silent-change problem this file exists to prevent.
    """
    source = __import__("pathlib").Path(__file__).read_text()
    missing = []
    for mod in (xas_policy, exafs_policy, xrs_policy):
        for name in dir(mod):
            if name.startswith("_") or name == "CITATIONS":
                continue
            if not name.isupper():
                continue
            if name not in source:
                missing.append(f"{mod.__name__.split('.')[-2]}.{name}")
    assert not missing, (
        "new policy constants are not pinned in tests/test_science_policy.py: "
        f"{missing}. Add an assertion so a future change to them is deliberate."
    )
