"""Postgres-backed scan data — for deployments where a converter pipeline
populates ``BL15-2_scan_metadata`` and pickle files for each scan.

Used by the S3DF/playground deployment (k8s, read-only PVC, separate
``bldata_converter`` sidecar). Implements the
:class:`~beamtimehero_cli.spec_data.backend.ScansBackend` Protocol so
tools can swap between this and ``FilesBackend`` without changes.

Connection settings come from the standard ``DB_HOST/PORT/NAME/USER/
PASSWORD`` env vars. Pickle directory comes from ``BL_PICKLE_DIR`` (and
``BL_SCAN_DIR`` is used to compute the relative path that maps a SPEC
source file to its pickle subdirectory).

Install with ``pip install 'beamtimehero_cli[postgres]'``.
"""
from __future__ import annotations

import json
import logging
import os
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from beamtimehero_cli.analysis import xas

logger = logging.getLogger(__name__)


_TABLE = '"BL15-2_scan_metadata"'


# ---------------------------------------------------------------------------
# Connection helpers (lazy)
# ---------------------------------------------------------------------------

def _connect():
    """Open a fresh psycopg2 connection from env vars.

    Raises ValueError with a clear message if the driver isn't installed
    or required env vars are missing.
    """
    try:
        import psycopg2
    except ImportError as e:
        raise ValueError(
            "psycopg2 not installed. Install with "
            "`pip install 'beamtimehero_cli[postgres]'`."
        ) from e

    missing = [k for k in ("DB_HOST", "DB_NAME", "DB_USER") if not os.environ.get(k)]
    if missing:
        raise ValueError(f"Postgres env vars not set: {', '.join(missing)}")

    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ.get("DB_PASSWORD", ""),
    )


def _pickle_dir() -> Path:
    return Path(os.environ.get("BL_PICKLE_DIR", "/sdf/group/ssrl/isaac/data/pickles"))


def _scan_dir() -> Path:
    return Path(os.environ.get("BL_SCAN_DIR", "/sdf/group/ssrl/isaac/data/data"))


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------

class PostgresBackend:
    """Scan-data backend backed by Postgres metadata + pickle DataFrames.

    Conforms to :class:`ScansBackend`. Each method opens and closes its
    own connection; that's fine at the call rates the agent generates,
    and matches the original playground pattern.
    """

    # --- ScansBackend Protocol --------------------------------------------

    def list_scans(self, limit: int = 20) -> list[dict]:
        with _connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT file_name, scan_number, scan_command, date_time, num_points,
                       counters, count_time, acquisition_seconds
                FROM {_TABLE}
                ORDER BY date_time DESC NULLS LAST, file_name, scan_number
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
            cur.close()

        return [
            {
                "file_name": r[0],
                "scan_number": r[1],
                "scan_command": r[2],
                "date_time": r[3].isoformat() if r[3] else None,
                "num_points": r[4],
                "counters": r[5],
                "count_time": r[6],
                "acquisition_seconds": r[7],
            }
            for r in rows
        ]

    def get_scan_metadata(self, file_name: str, scan_number: int) -> dict | None:
        with _connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT file_name, file_path, scan_number, scan_command, date_time,
                       epoch, motor_positions, counters, num_points,
                       count_time, acquisition_seconds
                FROM {_TABLE}
                WHERE file_name = %s AND scan_number = %s
                """,
                (file_name, scan_number),
            )
            row = cur.fetchone()
            cur.close()
        if not row:
            return None

        motor_positions = row[6]
        if isinstance(motor_positions, str):
            motor_positions = json.loads(motor_positions)

        return {
            "file_name": row[0],
            "file_path": row[1],
            "scan_number": row[2],
            "scan_command": row[3],
            "date_time": row[4].isoformat() if row[4] else None,
            "epoch": row[5],
            "motor_positions": motor_positions,
            "counters": row[7],
            "num_points": row[8],
            "count_time": row[9],
            "acquisition_seconds": row[10],
        }

    def read_scan(self, file_name: str, scan_number: int) -> pd.DataFrame | None:
        """Load the pickled DataFrame the converter wrote for this scan.

        Pickle location mirrors the source SPEC file's directory:
        ``BL_PICKLE_DIR / <experiment-subdir> / <file_name>_dir / <file_name>_S<NNN>.pkl``.
        """
        meta = self.get_scan_metadata(file_name, scan_number)
        if not meta or not meta.get("file_path"):
            return None
        source_path = Path(meta["file_path"])
        try:
            rel = source_path.parent.relative_to(_scan_dir())
        except ValueError:
            rel = Path(".")
        pickle_path = (
            _pickle_dir() / rel / f"{file_name}_dir" / f"{file_name}_S{scan_number:03d}.pkl"
        )
        if not pickle_path.exists():
            logger.warning("Pickle not found: %s", pickle_path)
            return None
        with open(pickle_path, "rb") as f:
            return pickle.load(f)

    def get_latest_scan(self) -> dict | None:
        scans = self.list_scans(limit=1)
        return scans[0] if scans else None

    def get_scan_deadtime(self, file_name: str, scan_number: int) -> dict | None:
        with _connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT acquisition_seconds, wall_clock_seconds, dead_time_seconds,
                       scan_command, num_points, count_time
                FROM {_TABLE}
                WHERE file_name = %s AND scan_number = %s
                """,
                (file_name, scan_number),
            )
            row = cur.fetchone()
            cur.close()
        if not row:
            return None
        acq, wall, dead, cmd, npts, ct = row
        pct = round(100 * dead / wall, 2) if (wall and dead is not None) else None
        return {
            "file_name": file_name,
            "scan_number": scan_number,
            "scan_command": cmd,
            "num_points": npts,
            "count_time": ct,
            "acquisition_seconds": acq,
            "wall_clock_seconds": wall,
            "dead_time_seconds": dead,
            "dead_time_pct": pct,
        }

    def get_scan_numbers_for_file(self, file_name: str) -> list[int]:
        with _connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT scan_number FROM {_TABLE} WHERE file_name = %s ORDER BY scan_number",
                (file_name,),
            )
            rows = cur.fetchall()
            cur.close()
        return [r[0] for r in rows]

    def get_most_recent_file(self) -> str | None:
        with _connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT file_name FROM {_TABLE}
                ORDER BY date_time DESC NULLS LAST
                LIMIT 1
                """
            )
            row = cur.fetchone()
            cur.close()
        return row[0] if row else None

    # --- Convenience ------------------------------------------------------

    def get_active_counter(self, file_name: str, scan_number: int) -> dict | None:
        df = self.read_scan(file_name, scan_number)
        if df is None:
            return None
        counter, reason = xas.pick_active_counter(df)
        return {
            "file_name": file_name,
            "scan_number": scan_number,
            "active_counter": counter,
            "reason": reason,
        }

    # --- Raw SQL (for the s3df psql branch) -------------------------------

    def execute_readonly_sql(self, query: str, max_rows: int = 100) -> dict:
        """Execute a read-only SELECT and return rows + columns.

        Rejects anything that isn't a SELECT or that includes write-like
        keywords (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE,
        GRANT, REVOKE). The connection user should be DB-level read-only
        in production; this is belt-and-suspenders.
        """
        q = query.strip().rstrip(";").strip()
        if not q.lower().startswith("select"):
            return {"ok": False, "error": "Only SELECT queries are allowed."}
        forbidden = (
            "insert ", "update ", "delete ", "drop ", "alter ",
            "create ", "truncate ", "grant ", "revoke ", ";--",
        )
        lc = " " + q.lower() + " "
        for kw in forbidden:
            if kw in lc:
                return {"ok": False, "error": f"Forbidden keyword: {kw.strip()}"}

        try:
            with _connect() as conn:
                cur = conn.cursor()
                try:
                    cur.execute(q)
                    cols = [d[0] for d in (cur.description or [])]
                    rows = cur.fetchmany(max_rows)
                finally:
                    cur.close()
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return {
            "ok": True,
            "columns": cols,
            "rows": [list(r) for r in rows],
            "row_count": len(rows),
            "truncated": len(rows) >= max_rows,
        }
