"""Action-log writes a row per CLI invocation."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    db_path = tmp_path / "action.db"
    monkeypatch.setenv("BEAMLINE_TOOLS_DB_PATH", str(db_path))
    monkeypatch.setenv("BEAMTIMEHERO_CLI_LOG", "1")
    monkeypatch.setenv("SPEC_MOCK", "1")
    # Reset cached config module so it picks up the new env path
    import importlib
    import beamtimehero_cli.config as cfg
    importlib.reload(cfg)
    import beamtimehero_cli.action_log.session as s
    importlib.reload(s)
    yield db_path


def test_ref_invocation_logs_row(fresh_db, capsys):
    from beamtimehero_cli.cli.__main__ import main
    rc = main(["ref", "--list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Available reference documents" in out

    conn = sqlite3.connect(fresh_db)
    rows = conn.execute(
        "select tree, exit_code from cliinvocationlog order by id desc limit 1"
    ).fetchall()
    assert len(rows) == 1
    tree, exit_code = rows[0]
    assert tree == "ref"
    assert exit_code == 0


def test_help_invocation_logs_row(fresh_db, capsys):
    from beamtimehero_cli.cli.__main__ import main
    with pytest.raises(SystemExit):
        main(["--help"])
    conn = sqlite3.connect(fresh_db)
    rows = conn.execute(
        "select exit_code from cliinvocationlog order by id desc limit 1"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 0  # --help exits 0
