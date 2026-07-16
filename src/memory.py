"""SQLite-backed run history + archived-attempts cache.

Two tables:

- ``runs`` — one row per ``pipeline.run()`` call. Records direction,
  method, started/finished, status, paper path, and the SOUL hash
  at run start (so we can later prove "this run used a particular
  version of the SOUL").

- ``archived`` — one row per ``PhDStudent.archive_attempt()`` call.
  Mirror of the YAML on disk, but queryable.

Both are written from the pipeline. Reads are exposed via the
``paperfessor memory`` CLI subcommand.

The DB lives at ``<workspace>/memory.sqlite3`` (see
:func:`src.paths.memory_db_path`). We use the stdlib :mod:`sqlite3`
only — no SQLAlchemy, no extra deps. Schema changes are applied
via :func:`_ensure_schema` on first use, so an empty DB file is
fine.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from src._meta import soul_sha256
from src.paths import ensure_dirs, memory_db_path

logger = logging.getLogger(__name__)

_lock = threading.RLock()


# ---- Schema ---------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    direction       TEXT NOT NULL,
    method          TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT NOT NULL,
    status          TEXT NOT NULL,
    paper_path      TEXT,
    note            TEXT,
    soul_sha256     TEXT,
    config_json     TEXT
);

CREATE INDEX IF NOT EXISTS runs_started_at ON runs (started_at DESC);
CREATE INDEX IF NOT EXISTS runs_status ON runs (status);

CREATE TABLE IF NOT EXISTS archived (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER,
    research_area   TEXT NOT NULL,
    research_direction TEXT NOT NULL,
    research_question  TEXT NOT NULL,
    method          TEXT NOT NULL,
    success         INTEGER NOT NULL,
    reason          TEXT,
    paper_path      TEXT,
    archived_at     TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs (id)
);

CREATE INDEX IF NOT EXISTS archived_method ON archived (method);
"""


# ---- Connection management ------------------------------------------------


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    ensure_dirs()
    path = Path(db_path) if db_path is not None else memory_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)  # autocommit
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def cursor(db_path: Path | None = None) -> Iterator[sqlite3.Cursor]:
    """Yield a cursor with schema ensured; commits on exit."""
    with _lock:
        conn = _connect(db_path)
    try:
        with _lock:
            for stmt in _SCHEMA.strip().split(";\n"):
                if stmt.strip():
                    conn.execute(stmt)
        cur = conn.cursor()
        yield cur
    finally:
        conn.close()


# ---- Writes ---------------------------------------------------------------


def record_run(
    *,
    direction: str,
    method: str,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    paper_path: str | None = None,
    note: str = "",
    config: dict[str, Any] | None = None,
) -> int:
    """Insert a row in ``runs``. Returns the row id."""
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO runs (direction, method, started_at, finished_at, status,
                              paper_path, note, soul_sha256, config_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                direction,
                method,
                started_at.isoformat(timespec="seconds"),
                finished_at.isoformat(timespec="seconds"),
                status,
                paper_path,
                note,
                soul_sha256() or "",
                json.dumps(config or {}, default=str),
            ),
        )
        run_id = cur.lastrowid
    return int(run_id) if run_id is not None else 0


def record_archived(
    *,
    research_area: str,
    research_direction: str,
    research_question: str,
    method: str,
    success: bool,
    reason: str = "",
    paper_path: str | None = None,
    run_id: int | None = None,
) -> int:
    """Insert a row in ``archived``. Returns the row id."""
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO archived (run_id, research_area, research_direction,
                                  research_question, method, success, reason,
                                  paper_path, archived_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                research_area,
                research_direction,
                research_question,
                method,
                1 if success else 0,
                reason,
                paper_path,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        archived_id = cur.lastrowid
    return int(archived_id) if archived_id is not None else 0


# ---- Reads ----------------------------------------------------------------


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    with cursor() as cur:
        cur.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,))
        return [dict(row) for row in cur.fetchall()]


def get_run(run_id: int) -> dict[str, Any] | None:
    with cursor() as cur:
        cur.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
        row = cur.fetchone()
        return dict(row) if row is not None else None


def list_archived(limit: int = 100) -> list[dict[str, Any]]:
    with cursor() as cur:
        cur.execute("SELECT * FROM archived ORDER BY archived_at DESC LIMIT ?", (limit,))
        return [dict(row) for row in cur.fetchall()]


def lookup_method(
    *, research_area: str, method: str, success_only: bool = True
) -> dict[str, Any] | None:
    """Return the most-recent archived row for ``method`` (or None)."""
    with cursor() as cur:
        if success_only:
            cur.execute(
                """
                SELECT * FROM archived
                WHERE research_area = ? AND method = ? AND success = 1
                ORDER BY archived_at DESC LIMIT 1
                """,
                (research_area, method),
            )
        else:
            cur.execute(
                """
                SELECT * FROM archived
                WHERE research_area = ? AND method = ?
                ORDER BY archived_at DESC LIMIT 1
                """,
                (research_area, method),
            )
        row = cur.fetchone()
        return dict(row) if row is not None else None


def stats() -> dict[str, Any]:
    with cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM runs")
        n_runs = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM runs WHERE status='ok'")
        n_ok = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM archived")
        n_archived = cur.fetchone()["n"]
    return {"runs": n_runs, "runs_ok": n_ok, "archived": n_archived}


__all__ = [
    "cursor",
    "get_run",
    "list_archived",
    "list_runs",
    "lookup_method",
    "record_archived",
    "record_run",
    "stats",
]
