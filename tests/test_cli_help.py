"""--help surface tests.

Confirm the top-level CLI exposes only the four generic trees plus `ref`,
and that no per-role agent branches (`blaligner`, `samplealigner`,
`collector`, `surveyor`) leak in.
"""
from __future__ import annotations

import io
import sys

import pytest

from beamtimehero_cli.cli.__main__ import _build_parser, main


EXPECTED_TREES = {"ref", "tool", "db", "spec-read", "spec-write"}
FORBIDDEN_TREES = {"blaligner", "samplealigner", "collector", "surveyor", "steering"}


def test_top_level_trees_exact():
    parser = _build_parser()
    # subparsers is the first positional subparsers action
    subactions = [a for a in parser._actions if isinstance(a, type(parser._subparsers._group_actions[0]))]  # type: ignore[attr-defined]
    sp = next(a for a in parser._actions if hasattr(a, "choices") and a.choices)
    trees = set(sp.choices.keys())
    assert trees == EXPECTED_TREES, f"unexpected trees: {trees ^ EXPECTED_TREES}"


def test_no_agent_role_trees():
    parser = _build_parser()
    sp = next(a for a in parser._actions if hasattr(a, "choices") and a.choices)
    leaked = FORBIDDEN_TREES & set(sp.choices.keys())
    assert not leaked, f"forbidden trees leaked into CLI: {leaked}"


def test_help_prints_and_exits_zero(capsys, monkeypatch):
    monkeypatch.setenv("BEAMTIMEHERO_CLI_LOG", "0")
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    # argparse exits 0 on --help
    assert exc_info.value.code in (0, None)
    out = capsys.readouterr().out
    for tree in EXPECTED_TREES:
        assert tree in out
