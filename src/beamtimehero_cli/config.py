"""Configuration for the beamtimehero_cli package.

Owns: SPEC transport, sqlite path, beamline scan/log directories, timezone,
and CLI invocation logging knobs. All values resolve from environment
variables (loaded from a .env file in the caller's CWD if present).

This module is project-agnostic: no orchestration, LLM, or web concerns.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent  # repo root (where pyproject.toml lives)
DATA_DIR = Path(os.environ.get("BEAMTIMEHERO_DATA_DIR", str(PROJECT_ROOT / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# SPEC dispatcher — defaults to mock so the CLI is usable off-beamline.
# ---------------------------------------------------------------------------
SPEC_SCREEN_NAME = "spec"
SPEC_POLL_INTERVAL_S = 2.0
SPEC_PROMPT_REGEX = r"^\d+\.SPEC> ?$"
SPEC_MOCK = os.getenv("SPEC_MOCK", "1") == "1"

# Transport: "tcp" (spec server binary protocol), "screen" (GNU screen
# stuffing), "sandbox" (HTTP API to sim-mode SPEC).
SPEC_TRANSPORT = os.getenv("SPEC_TRANSPORT", "tcp")
SPEC_HOST = os.getenv("SPEC_HOST", "localhost")
SPEC_PORT = int(os.getenv("SPEC_PORT", "2033"))
SPEC_NAME = os.getenv("SPEC_NAME", "spec")

SPEC_EVAL_URL = os.getenv("SPEC_EVAL_URL", "http://127.0.0.1:5006")

# ---------------------------------------------------------------------------
# Action log SQLite — independent of any external schema.
# ---------------------------------------------------------------------------
DB_PATH = os.environ.get("BEAMLINE_TOOLS_DB_PATH", str(DATA_DIR / "beamline_tools.db"))
os.environ.setdefault("BEAMLINE_TOOLS_DB_PATH", DB_PATH)

# ---------------------------------------------------------------------------
# CLI invocation log — one row per `beamtimehero` call.
# ---------------------------------------------------------------------------
CLI_LOG_ENABLED = os.getenv("BEAMTIMEHERO_CLI_LOG", "1") == "1"
CLI_LOG_MAX_RESULT_BYTES = int(os.getenv("BEAMTIMEHERO_CLI_LOG_MAX_BYTES", "65536"))

TOOLS_MODE = os.getenv("TOOLS_MODE", "cli")

# ---------------------------------------------------------------------------
# EPICS PVs (reference only — not wired here)
# ---------------------------------------------------------------------------
EPICS_PV_SPEAR_CURRENT = "SPEAR:BeamCurrAvg"
EPICS_PV_BL_STATE = "BL15:State"
EPICS_PV_GAP_OWNER = "BL15:GapOwnerNode"

# ---------------------------------------------------------------------------
# Beamline data directories and timezone
# ---------------------------------------------------------------------------
BL_TIMEZONE = ZoneInfo("America/Los_Angeles")


def now_pacific() -> datetime:
    """Current time in Pacific, naive datetime for comparison."""
    return datetime.now(BL_TIMEZONE).replace(tzinfo=None)


_SAMPLE_DATA = PACKAGE_ROOT / "sample_data"

BL_LOGS_DIR = Path(os.getenv("BL_LOGS_DIR", "/usr/local/lib/spec.log/logfiles"))
if not BL_LOGS_DIR.exists():
    BL_LOGS_DIR = _SAMPLE_DATA

_DATA_ROOT = Path(os.getenv("BL_SCAN_DIR", "/data/fifteen"))


def _resolve_scan_dir(root: Path) -> Path:
    """Pick the most recently modified YYYY-mm_* subdirectory, or fall back."""
    if root.is_dir():
        if re.match(r"\d{4}-\d{2}_", root.name):
            return root
        subdirs = [d for d in root.iterdir()
                   if d.is_dir() and re.match(r"\d{4}-\d{2}_", d.name)]
        if subdirs:
            return max(subdirs, key=lambda d: d.stat().st_mtime)
    return _SAMPLE_DATA


BL_SCAN_DIR = _resolve_scan_dir(_DATA_ROOT)


def set_scan_dir(name: str) -> Path:
    """Set BL_SCAN_DIR to a subdirectory of the data root.

    Pass 'auto' to re-run auto-detection.
    """
    global BL_SCAN_DIR

    if name == "auto":
        BL_SCAN_DIR = _resolve_scan_dir(_DATA_ROOT)
        logger.info("Scan directory auto-detected: %s", BL_SCAN_DIR)
        return BL_SCAN_DIR

    target = _DATA_ROOT / name
    if not target.is_dir():
        raise ValueError(f"Directory does not exist: {target}")

    BL_SCAN_DIR = target
    logger.info("Scan directory set to: %s", BL_SCAN_DIR)
    return BL_SCAN_DIR


LOG_FILE_PATTERN = "log__*"

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
MAX_LOG_LINES = 1000

# ---------------------------------------------------------------------------
# Sample camera (RPi-Cam snapshot endpoint)
# ---------------------------------------------------------------------------
SAMPLE_CAM_HOST = os.getenv("SAMPLE_CAM_HOST", "192.168.150.93")
SAMPLE_CAM_PORT = int(os.getenv("SAMPLE_CAM_PORT", "8080"))
SAMPLE_CAM_DEFAULT_QUALITY = int(os.getenv("SAMPLE_CAM_QUALITY", "50"))
