"""Tests for agent profiles (Phase 3).

Profiles register a curated top-level branch (``beamtimehero k8s-agent <leaf>``)
whose leaves alias canonical ``(tree, ..., name)`` paths. The master catalog
must stay unchanged and routing must reach the same dispatcher state the
canonical leaf would set.
"""
from __future__ import annotations

import importlib
import sys

import pytest


@pytest.fixture
def parser_module():
    """Reload cli.__main__ so profile discovery picks up any modules
    written by tests during this session."""
    from beamtimehero_cli.cli import profiles as profiles_pkg
    importlib.reload(profiles_pkg)
    main_mod = importlib.import_module("beamtimehero_cli.cli.__main__")
    importlib.reload(main_mod)
    return main_mod


def test_profile_discovery_finds_bl_aligner(parser_module):
    from beamtimehero_cli.cli.profiles import PROFILES
    assert "bl-aligner" in PROFILES
    assert PROFILES["bl-aligner"]["name"] == "bl-aligner"
    assert len(PROFILES["bl-aligner"]["aliases"]) > 0


def test_register_profile_adds_to_known_set(parser_module):
    from beamtimehero_cli.cli.profiles import PROFILES, register_profile
    register_profile({
        "name": "test-extra",
        "description": "registered out-of-tree",
        "aliases": {"list-scans": ("s3df", "list_scans")},
    })
    try:
        assert "test-extra" in PROFILES
        # The profile aliases are reachable through the built parser.
        parser = parser_module.build_parser()
        args = parser.parse_args(["test-extra", "list-scans", "--limit", "3"])
        assert args._tool_category == ("s3df",)
        assert args._tool_name == "list_scans"
    finally:
        del PROFILES["test-extra"]


def test_register_profile_rejects_empty_name():
    from beamtimehero_cli.cli.profiles import register_profile
    with pytest.raises(ValueError):
        register_profile({"aliases": {}})


def test_bl_aligner_list_scans_routes_to_spec_file(parser_module):
    parser = parser_module.build_parser()
    args = parser.parse_args(["bl-aligner", "list-scans"])
    assert args._tool_category == ("spec-file",)
    assert args._tool_name == "list_scans"


def test_help_shows_profile_trees(parser_module, capsys):
    parser = parser_module.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])
    captured = capsys.readouterr()
    assert "bl-aligner" in captured.out


def test_list_profiles_flag(parser_module, capsys):
    rc = parser_module.run_with(
        parser_module.build_parser, parser_module.dispatch,
        ["--list-profiles"],
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "bl-aligner" in out
    assert "alias" in out


def test_profile_leaves_do_not_pollute_canonical_trees(parser_module, capsys):
    """`beamtimehero s3df --help` lists s3df's canonical leaves and the
    psql sub-branch only — no profile aliases should leak in."""
    parser = parser_module.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["s3df", "--help"])
    out = capsys.readouterr().out
    # canonical underscore-form names appear (categorize keeps original name
    # but build_catalog_subtrees converts to kebab); check kebab.
    assert "list-scans" in out
    assert "psql" in out
    # Profile branches themselves shouldn't be reachable from inside s3df.
    assert "k8s-agent" not in out
    assert "bl-aligner" not in out


def test_profile_name_collision_raises(parser_module, monkeypatch):
    """A profile that picks a canonical tree name must raise at parser build."""
    from beamtimehero_cli.cli import profiles as profiles_pkg
    monkeypatch.setitem(profiles_pkg.PROFILES, "tool", {
        "name": "tool",
        "description": "would shadow canonical tool branch",
        "aliases": {},
    })
    with pytest.raises(RuntimeError, match="collides"):
        parser_module.build_parser()
    monkeypatch.delitem(profiles_pkg.PROFILES, "tool")


def test_unknown_canonical_path_logs_and_skips(parser_module, caplog):
    """An alias pointing at a non-existent canonical tool warns and skips."""
    from beamtimehero_cli.cli import profiles as profiles_pkg
    profiles_pkg.PROFILES["test-bad-alias"] = {
        "name": "test-bad-alias",
        "description": "test fixture",
        "aliases": {"phantom-leaf": ("tool", "does_not_exist_anywhere")},
    }
    try:
        with caplog.at_level("WARNING"):
            parser = parser_module.build_parser()
        # parser still builds; just no phantom-leaf under the bad branch
        assert any(
            "phantom-leaf" in rec.message or "does_not_exist_anywhere" in rec.message
            for rec in caplog.records
        )
    finally:
        del profiles_pkg.PROFILES["test-bad-alias"]
