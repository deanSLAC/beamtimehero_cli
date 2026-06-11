"""Unit tests for the local_data scan-metadata cache.

Covers:
- atomic + locked sidecar writes, and graceful handling of valid-JSON-
  wrong-type cache content (items: cache atomicity / robustness)
- (mtime, size) invalidation, with signatures recorded only after a
  successful parse (failed parses retry)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from beamtimehero_cli import config as bl_config
from beamtimehero_cli.spec_data import local_data


def _write_spec(path: Path, n_scans: int = 1, start_scan: int = 1) -> None:
    lines = [
        f"#F {path}",
        "#E 1700000000",
        "#D Wed Jun 11 10:00:00 2026",
        "#O0 Sx  Sy  Sz",
        "",
    ]
    for i in range(n_scans):
        sn = start_scan + i
        lines += [
            f"#S {sn}  ascan  energy 7100 7110 2 1",
            "#D Wed Jun 11 10:00:00 2026",
            "#T 1  (Seconds)",
            "#P0 1 2 3",
            "#N 4",
            "#L energy  Epoch  I0  I1",
            "7100 0 100 10",
            "7105 1 100 11",
            "7110 2 100 12",
            "",
        ]
    path.write_text("\n".join(lines))


@pytest.fixture
def scan_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(bl_config, "BL_SCAN_DIR", tmp_path)
    local_data.clear_cache()
    yield tmp_path
    local_data.clear_cache()


def _cache_file(scan_dir: Path) -> Path:
    return local_data._get_cache_file()


# ---------------------------------------------------------------------------
# Item 1: atomic writes, locking, wrong-type cache content
# ---------------------------------------------------------------------------

def test_cache_round_trip_and_atomic_write(scan_dir):
    _write_spec(scan_dir / "sample1")
    cache = local_data._load_cache()
    assert isinstance(cache, dict) and cache, "cache should hold parsed scans"

    cache_file = _cache_file(scan_dir)
    assert cache_file.exists()
    # Atomic save: no temp leftovers
    leftovers = [p for p in scan_dir.iterdir() if p.name.endswith(".tmp")]
    assert not leftovers, f"temp files left behind: {leftovers}"
    # Cache file is valid JSON dict
    assert isinstance(json.loads(cache_file.read_text()), dict)


def test_lock_sidecar_created(scan_dir):
    _write_spec(scan_dir / "sample1")
    local_data._load_cache()
    cache_file = _cache_file(scan_dir)
    lock = cache_file.with_name(cache_file.name + ".lock")
    assert lock.exists()


@pytest.mark.parametrize("bad_content", ["null", "[1, 2, 3]", '"a string"', "42"])
def test_wrong_type_cache_content_rebuilds(scan_dir, bad_content):
    _write_spec(scan_dir / "sample1")
    cache_file = _cache_file(scan_dir)
    cache_file.write_text(bad_content)

    cache = local_data._load_cache()  # must not raise AttributeError
    assert isinstance(cache, dict) and cache
    # Rebuilt cache was re-persisted as a dict
    assert isinstance(json.loads(cache_file.read_text()), dict)


def test_non_dict_entries_dropped(scan_dir):
    _write_spec(scan_dir / "sample1")
    cache_file = _cache_file(scan_dir)
    cache_file.write_text(json.dumps({"garbage::1": 12345}))

    cache = local_data._load_cache()  # must not raise on entry.get()
    assert isinstance(cache, dict)
    assert all(isinstance(v, dict) for v in cache.values())
    # The real SPEC file got (re)parsed since the garbage entry carried no signature
    assert any(v.get("file_name") == "sample1" for v in cache.values())


def test_corrupt_json_rebuilds(scan_dir):
    _write_spec(scan_dir / "sample1")
    cache_file = _cache_file(scan_dir)
    cache_file.write_text('{"truncated": ')

    cache = local_data._load_cache()
    assert isinstance(cache, dict) and cache


# ---------------------------------------------------------------------------
# Item 2: (mtime, size) invalidation; signature recorded only after success
# ---------------------------------------------------------------------------

def test_size_change_with_same_mtime_is_detected(scan_dir):
    spec = scan_dir / "sample1"
    _write_spec(spec, n_scans=1)
    cache = local_data._load_cache()
    assert len(cache) == 1
    st = spec.stat()

    # Rewrite with an extra scan but force the original mtime back
    _write_spec(spec, n_scans=2)
    os.utime(spec, (st.st_atime, st.st_mtime))
    assert spec.stat().st_mtime == st.st_mtime  # mtime unchanged, size changed

    cache = local_data._load_cache()
    assert len(cache) == 2, "size-only change must trigger re-parse"


def test_failed_parse_is_retried_on_next_call(scan_dir):
    spec = scan_dir / "sample1"
    _write_spec(spec)

    class _Boom:
        def __init__(self, *_a, **_k):
            raise RuntimeError("simulated parse failure")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(local_data, "SpecFile", _Boom)
        cache = local_data._load_cache()
        assert cache == {}
        assert str(spec) not in local_data._cached_file_sigs, (
            "signature must not be recorded for a failed parse"
        )

    cache = local_data._load_cache()
    assert len(cache) == 1, "file must be re-parsed after an earlier failure"
    assert str(spec) in local_data._cached_file_sigs


# ---------------------------------------------------------------------------
# Item 3: one SpecFile parse per file for multi-scan operations
# ---------------------------------------------------------------------------

def test_specfile_parsed_once_for_repeated_scan_reads(scan_dir):
    spec = scan_dir / "sample1"
    _write_spec(spec, n_scans=3)
    local_data._load_cache()
    local_data._specfile_handles.clear()

    count = {"n": 0}
    real = local_data.SpecFile

    def _counting(path):
        count["n"] += 1
        return real(path)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(local_data, "SpecFile", _counting)
        for sn in (1, 2, 3):
            df = local_data.read_processed_scan("sample1", sn)
            assert df is not None
    assert count["n"] == 1, "reading N scans of one unchanged file must parse it once"


def test_specfile_handle_invalidated_on_change(scan_dir):
    spec = scan_dir / "sample1"
    _write_spec(spec, n_scans=1)
    assert local_data.read_processed_scan("sample1", 1) is not None

    _write_spec(spec, n_scans=2)
    local_data._load_cache()
    df = local_data.read_processed_scan("sample1", 2)
    assert df is not None, "appended scan must be visible after the file changed"


def test_unchanged_file_not_reparsed(scan_dir, monkeypatch):
    spec = scan_dir / "sample1"
    _write_spec(spec)
    local_data._load_cache()

    calls = []
    real_parse = local_data._parse_spec_files

    def _spy(files):
        calls.append(list(files))
        return real_parse(files)

    monkeypatch.setattr(local_data, "_parse_spec_files", _spy)
    local_data._load_cache()
    assert calls == [], "unchanged files must not be re-parsed"
