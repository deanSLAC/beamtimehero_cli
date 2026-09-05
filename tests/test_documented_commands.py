"""Every `beamtimehero ...` command in the docs must actually parse.

Three of these were broken simultaneously: the README quick start invoked
`beamtimehero tool list-scans` after that tool moved to the `spec-file`
branch, the profiles refdoc demonstrated a profile registered only in a
consuming app, and the `run_command` tool description — the text an LLM reads
before its first call — gave an example with no tree segment at all.

Prose drifts from a CLI silently. This makes it loud, at the moment of the
change rather than on someone else's first day.
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

DOC_PATHS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "CONTRIBUTING.md",
    *sorted((REPO_ROOT / "src" / "beamtimehero_cli" / "refdocs" / "defaults").glob("*.md")),
    REPO_ROOT / "src" / "beamtimehero_cli" / "tool_catalog" / "cli_tool.py",
]

# Fragments that mark an illustrative form rather than a runnable command:
# a shell-permission glob, an elided argument list, an optional-flag summary.
_PLACEHOLDER_MARKERS = (":*", "\u2026", "...", "[", "]", "<", ">", "$", "{", "}")

# Only fenced code blocks are scanned in markdown. Prose says things like
# "driving beamtimehero from an agent", which is not a command and should not
# be parsed as one.
_FENCE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.S)

# In Python sources, the runnable examples live inside quoted strings.
_QUOTED = re.compile(r"['\"]([^'\"]*beamtimehero [^'\"]*)['\"]")

_CMD = re.compile(r"^\s*(?:[A-Z_]+=\S+\s+)*(beamtimehero\s.*?)\s*$")


def _candidate_lines(path: Path) -> list[str]:
    text = path.read_text()
    if path.suffix == ".py":
        # Sentence-embedded examples: take the quoted run, then the command.
        out = []
        for chunk in _QUOTED.findall(text):
            for m in re.finditer(r"beamtimehero [a-z0-9 _-]+", chunk):
                out.append(m.group(0).strip())
        return out
    return [
        line
        for block in _FENCE.findall(text)
        for line in block.splitlines()
    ]


def _documented_commands() -> list[tuple[str, str]]:
    """(doc, command) for every runnable `beamtimehero ...` line in the docs."""
    found: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for path in DOC_PATHS:
        if not path.exists():
            continue
        rel = str(path.relative_to(REPO_ROOT))
        for line in _candidate_lines(path):
            # Only the beamtimehero end of a pipeline is ours to validate.
            line = line.split("#")[0].split("|")[0].strip()
            m = _CMD.match(line)
            if not m:
                continue
            cmd = m.group(1).strip()
            if cmd == "beamtimehero":
                continue
            if any(mark in cmd for mark in _PLACEHOLDER_MARKERS):
                continue
            if (rel, cmd) in seen:
                continue
            seen.add((rel, cmd))
            found.append((rel, cmd))
    return found


_COMMANDS = _documented_commands()


def test_the_scan_found_commands():
    """Guard the guard: a regex that matches nothing would pass everything."""
    assert len(_COMMANDS) > 15, (
        f"only found {len(_COMMANDS)} documented commands — the extraction "
        "regex probably stopped matching"
    )


@pytest.mark.parametrize(
    "doc,cmd", _COMMANDS, ids=[f"{d}::{c[:60]}" for d, c in _COMMANDS]
)
def test_documented_command_parses(doc, cmd, monkeypatch, capsys):
    """The command must reach a real leaf (or --help), not an argparse error."""
    from beamtimehero_cli.cli.__main__ import build_parser

    argv = shlex.split(cmd)[1:]  # drop the program name
    if not argv:
        pytest.skip("bare program name")

    parser = build_parser()
    try:
        parser.parse_args(argv)
    except SystemExit as e:
        # ToolParser.error() exits 2 after printing {"ok": false, ...}.
        # --help exits 0, which is a valid documented command.
        if e.code not in (0, None):
            out = capsys.readouterr().out.strip()
            pytest.fail(
                f"{doc} documents `{cmd}`, which the real parser rejects:\n"
                f"  {out}\n"
                "Fix the doc, or the command."
            )
