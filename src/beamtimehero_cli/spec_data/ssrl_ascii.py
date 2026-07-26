"""SSRL EXAFS Data Collector 4.0 ASCII format — parsing layer.

SSRL beamlines (BL 4-3 style) write one ASCII file per sweep, named
``<sample>_<NNN>_A.<MMM>`` (NNN = scan number, MMM = sweep/repeat), plus a
same-named configuration directory holding ``.exp`` (experiment), ``.rgn``
(scan regions), ``.det`` (detector channel map) and ``profile.txt`` (motor
snapshot). File layout::

    Line 1   : "SSRL   EXAFS Data Collector 4.0"
    Line 2   : timestamp ("Thu Nov 20 02:18:52 2025")
    Line 3   : "PTS: <n> COLS: <m>"
    Line 4/5 : detector file / region file names
    Line 6/7 : beamline + low-signal config strings
    Lines 8-13: six free-text comment lines
    "Weights:" + row, "Offsets:" + row, "Data:" + <m> column-label lines
    <n> whitespace-separated data rows of <m> values

The header offsets (dark currents) are ALREADY applied to the stored
I0/I1/I2/Lytle columns; they are parsed for provenance only.

This module produces DataFrames in the house shape (index = scanned axis,
columns = counters, metadata in ``df.attrs``) so everything downstream of
``spec_data`` treats SSRL sweeps like any other scan. Two virtual counters
are appended when the 7-element Xspress3 columns are present:

- ``SCA_sum``  = ΣSCA1_1..7 — the summed windowed fluorescence. This is the
  standard signal counter for these files (the Athena projects SSRL ships
  use the same sum over I0). Explicit-counter discipline applies: pass
  ``counter="SCA_sum"``, don't rely on auto-picking.
- ``ICR_sum``  = ΣICR1_1..7 — for deadtime estimates.

Validated against SSRL BL 4-3 beamtimes 2025-07 (Ti K) and 2025-11 (S K);
ported from the webxas-data prototype (py-analysis/ssrl_parser.py).

This module is the single source of truth for the format. The chemcatal web
app carries a copy of the parsing half in chemcatal/xas_core/ssrl_collector.py
(its notebook image installs xas_core without beamtimehero_cli) — KEEP THE TWO
IN SYNC when editing the parsers here.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

FLUOR_PREFIX = "SCA1_"
ICR_PREFIX = "ICR1_"

# ``<sample>_<NNN>_A.<MMM>`` — the ASCII sweep-file naming convention.
SWEEP_RE = re.compile(r"^(?P<stem>.+)_(?P<scan>\d{3})_A\.(?P<sweep>\d{3})$")


def is_ssrl_ascii(path: str | Path) -> bool:
    """Cheap sniff: the SSRL Data Collector banner, in a genuinely-ASCII file.

    The collector writes a parallel binary/ variant whose first line carries
    the same banner but with NUL separators throughout — the NUL check keeps
    those (and any other binary look-alike) out.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(256)
    except OSError:
        return False
    first = head.split(b"\n", 1)[0]
    return b"SSRL" in first and b"Data Collector" in first and b"\x00" not in head


def parse_sweep_name(filename: str) -> dict | None:
    """Split '<sample>_<NNN>_A.<MMM>' into sample stem / scan no / sweep no."""
    m = SWEEP_RE.match(filename)
    if not m:
        return None
    return {
        "sample": m.group("stem"),
        "scan_number": int(m.group("scan")),
        "sweep": int(m.group("sweep")),
    }


def read_ssrl_scan(path: str | Path) -> pd.DataFrame:
    """Parse one SSRL ASCII sweep file into the house DataFrame shape.

    Index = the energy axis ("Achieved Energy" when present, else
    "Requested Energy", else the first column — alignment scans index on
    their scanned motor). Columns = all recorded counters plus the
    ``SCA_sum``/``ICR_sum`` virtual counters when Xspress3 channels exist.

    ``df.attrs`` carries: ``date_time``, ``count_time`` (median of the real
    time clock), ``scan_command`` (synthesized), ``counters``,
    ``num_points``, ``npts_header``, ``is_complete`` (aborted sweeps store
    fewer rows than the header promises), ``detector_file``,
    ``region_file``, ``comments`` (the non-empty header comment lines),
    ``weights``, ``offsets``, ``motor_positions`` (from a sibling
    ``profile.txt`` when the config directory exists).

    Raises ValueError when the file is not an SSRL Data Collector ASCII.
    """
    path = Path(path)
    lines = path.read_text(errors="replace").splitlines()
    if not lines or "SSRL" not in lines[0]:
        raise ValueError(f"{path}: not an SSRL Data Collector ASCII file")

    m = re.search(r"PTS:\s*(\d+)\s+COLS:\s*(\d+)", lines[2])
    if not m:
        raise ValueError(f"{path}: missing PTS/COLS header line")
    npts_header, ncols = int(m.group(1)), int(m.group(2))

    def _find_marker(marker: str) -> int:
        for i, line in enumerate(lines):
            if line.strip().rstrip(":") == marker:
                return i
        raise ValueError(f"{path}: no '{marker}:' line")

    iw, io_, id_ = _find_marker("Weights"), _find_marker("Offsets"), _find_marker("Data")
    weights = [float(v) for v in lines[iw + 1].split()]
    offsets = [float(v) for v in lines[io_ + 1].split()]
    labels = [lines[id_ + 1 + k].strip() for k in range(ncols)]

    rows = []
    for line in lines[id_ + 1 + ncols:]:
        vals = line.split()
        if len(vals) == ncols:
            try:
                rows.append([float(v) for v in vals])
            except ValueError:
                continue
    data = np.array(rows) if rows else np.zeros((0, ncols))

    df = pd.DataFrame(data, columns=labels)
    # virtual counters for the 7-element Xspress3
    sca_cols = [c for c in labels if c.startswith(FLUOR_PREFIX)]
    icr_cols = [c for c in labels if c.startswith(ICR_PREFIX)]
    if sca_cols:
        df["SCA_sum"] = df[sca_cols].sum(axis=1)
    if icr_cols:
        df["ICR_sum"] = df[icr_cols].sum(axis=1)

    # index on the energy axis (falls back for motor/alignment scans)
    for axis in ("Achieved Energy", "Requested Energy"):
        if axis in df.columns:
            df = df.set_index(axis)
            break
    else:
        df = df.set_index(labels[0])

    count_time = None
    if "Real time clock" in df.columns and len(df):
        count_time = float(np.median(df["Real time clock"].values))

    region_file = lines[4].strip()
    comments = [l.strip() for l in lines[7:13] if l.strip()]
    df.attrs = {
        "date_time": lines[1].strip(),
        "count_time": count_time,
        "scan_command": f"ssrl_xas {region_file}" if region_file else "ssrl_xas",
        "counters": list(df.columns),
        "num_points": len(df),
        "npts_header": npts_header,
        "is_complete": len(df) >= npts_header,
        "detector_file": lines[3].strip(),
        "region_file": region_file,
        "beamline_config": lines[5].strip(),
        "comments": comments,
        "weights": weights,
        "offsets": offsets,
        "motor_positions": _sibling_motor_positions(path),
    }
    return df


def _sibling_motor_positions(sweep_path: Path) -> dict:
    """Motor snapshot from the scan's config directory, when present.

    The config dir is the sweep filename with the ``_A.MMM`` suffix removed
    (``01_foo_072_A.003`` → ``01_foo_072/profile.txt``).
    """
    stem = re.sub(r"_A\.\d{3}$", "", sweep_path.name)
    profile = sweep_path.parent / stem / "profile.txt"
    if not profile.is_file():
        return {}
    return read_profile(profile)


# ---------------------------------------------------------------------------
# Config-file parsers
# ---------------------------------------------------------------------------

def read_profile(path: str | Path) -> dict:
    """Parse a ``profile.txt`` motor snapshot → {device: achieved_position}."""
    positions: dict[str, float] = {}
    device = None
    for line in Path(path).read_text(errors="replace").splitlines():
        m = re.match(r"^Device:\s+(\S+)", line)
        if m:
            device = m.group(1)
            continue
        m = re.match(r"^Channel:\s+2\s+Achieved Pos\.\s+(-?[\d.]+)", line)
        if m and device:
            positions[device] = float(m.group(1))
    return positions


def read_rgn(path: str | Path) -> dict:
    """Parse an XAS region (.rgn) file → energy regions.

    Region rows carry ``idx e_start e_stop step npts time ...``; the file
    also holds NOTE lines and summary rows which are skipped.
    """
    lines = Path(path).read_text(errors="replace").splitlines()
    out: dict = {"file": str(path), "notes": [], "regions": []}
    for line in lines[1:]:
        if line.startswith("NOTE"):
            out["notes"].append(line.split(":", 1)[1].strip().strip('"'))
            continue
        vals = line.split()
        if not vals or not all(re.fullmatch(r"-?\d+\.?\d*", v) for v in vals):
            continue
        row = [float(v) for v in vals]
        if len(row) >= 5 and row[0] >= 1 and row[1] > row[0]:
            out["regions"].append(
                {"start": row[1], "stop": row[2], "step": row[3], "npts": int(row[4])}
            )
    return out


def read_exp(path: str | Path) -> dict:
    """Parse an experiment (.exp) file: simple ``KEY:<tab>value`` pairs."""
    out: dict[str, str] = {}
    for line in Path(path).read_text(errors="replace").splitlines():
        m = re.match(r"^([A-Z_0-9]+):\s*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"')
    return out


def read_det(path: str | Path) -> dict:
    """Parse a detector (.det) file → devices with their channel maps."""
    meta = read_exp(path)  # the scalar header shares the KEY: value format
    devices: list[dict] = []
    cur: dict | None = None
    for line in Path(path).read_text(errors="replace").splitlines():
        if line.startswith("DEVICE_NAME:"):
            cur = {"name": line.split(":", 1)[1].strip(), "channels": []}
            devices.append(cur)
        elif line.startswith("CHANNEL:") and cur is not None:
            parts = line.split(":", 1)[1].split()
            label = re.search(r'"([^"]*)"', line)
            cur["channels"].append(
                {
                    "on": parts[0] == "ON",
                    "index": int(parts[1]),
                    "offset": float(parts[2]),
                    "label": label.group(1) if label else "",
                }
            )
    meta["devices"] = devices
    return meta


# ---------------------------------------------------------------------------
# Directory scanning
# ---------------------------------------------------------------------------

def group_sweeps(
    directory: str | Path, include_align: bool = False,
) -> dict[str, list[Path]]:
    """Group the sweep files in a dataset directory by sample+scan number.

    Returns ``{"<sample>_<NNN>": [Path(_A.001), Path(_A.002), ...]}`` with
    sweeps in order. Alignment scans (``align*``) are motor scans, not XAS,
    and are skipped unless ``include_align``.
    """
    directory = Path(directory)
    groups: dict[str, list[Path]] = {}
    for f in sorted(directory.iterdir()):
        if not f.is_file():
            continue
        info = parse_sweep_name(f.name)
        if info is None:
            continue
        if not include_align and info["sample"].startswith("align"):
            continue
        key = f"{info['sample']}_{info['scan_number']:03d}"
        groups.setdefault(key, []).append(f)
    return groups
