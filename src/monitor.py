"""Passive + active monitoring for the 3-agent model.

- **Passive**: triggered when a worker writes to its log
  (``research_log.md`` or ``code_log.md``). Watches log mtime.
- **Active**: 2-minute timer polls worker status. Fires the PhD's
  idle callback if a worker has been non-idle for too long without
  a new log entry.
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

ACTIVE_TIMEOUT_SECONDS: float = 120.0
ACTIVE_POLL_INTERVAL_SECONDS: float = 30.0


class WorkerName(str, Enum):
    MS = "ms"
    UG = "ug"


_WORKER_LOG_FILES: dict[WorkerName, str] = {
    WorkerName.MS: "shared/research_log.md",
    WorkerName.UG: "shared/code_log.md",
}


class Supervisor:
    """Watches the workspace for worker activity and fires callbacks."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = Path(workspace)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_mtime: dict[WorkerName, float] = {}
        self._last_idle_check: dict[WorkerName, float] = {}
        self.on_worker_report: Callable[[WorkerName, Path], None] | None = None
        self.on_worker_idle: Callable[[WorkerName, float], None] | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._init_mtime_baseline()
        self._thread = threading.Thread(
            target=self._run, name="paperfessor-supervisor", daemon=True
        )
        self._thread.start()
        logger.info("supervisor started (workspace=%s)", self._workspace)

    def stop(self, *, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        logger.info("supervisor stopped")

    def _init_mtime_baseline(self) -> None:
        for name, relpath in _WORKER_LOG_FILES.items():
            p = self._workspace / relpath
            self._last_mtime[name] = p.stat().st_mtime if p.exists() else 0.0
            self._last_idle_check[name] = time.monotonic()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception:  # noqa: BLE001
                logger.exception("supervisor tick raised; continuing")
            self._stop_event.wait(ACTIVE_POLL_INTERVAL_SECONDS)

    def _tick(self) -> None:
        now = time.monotonic()
        for name, relpath in _WORKER_LOG_FILES.items():
            log_path = self._workspace / relpath
            if not log_path.exists():
                continue
            try:
                mtime = log_path.stat().st_mtime
            except OSError:
                continue
            if mtime > self._last_mtime.get(name, 0.0):
                self._last_mtime[name] = mtime
                self._last_idle_check[name] = now
                if self.on_worker_report is not None:
                    try:
                        self.on_worker_report(name, log_path)
                    except Exception:  # noqa: BLE001
                        logger.exception("on_worker_report raised; continuing")
                continue
            last_check = self._last_idle_check.get(name, now)
            if now - last_check >= ACTIVE_TIMEOUT_SECONDS:
                self._last_idle_check[name] = now
                if self.on_worker_idle is not None:
                    try:
                        self.on_worker_idle(name, now - mtime)
                    except Exception:  # noqa: BLE001
                        logger.exception("on_worker_idle raised; continuing")


__all__ = [
    "ACTIVE_POLL_INTERVAL_SECONDS",
    "ACTIVE_TIMEOUT_SECONDS",
    "Supervisor",
    "WorkerName",
]
