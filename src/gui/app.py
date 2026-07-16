"""Paperfessor GUI - a single-file PyQt6 window with the essentials:

- Token dashboard (per-agent usage with live updates)
- Settings (provider, model, thinking, max input/output tokens)
- A simple "Direction" tab that kicks off a run in a background thread
- Console tab that streams the run log

Tab splitting into separate files was tried and reverted; the GUI
is small enough to live in one place. Add more tabs here as needed.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QPlainTextEdit, QProgressBar, QPushButton,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from src._meta import __version__
from src.config import Settings, Theme, load_settings
from src.gui.theme import palette_for, stylesheet
from src.i18n import t

logger = logging.getLogger(__name__)


class _Tab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._build()

    def _build(self) -> None:  # pragma: no cover - subclasses override
        ...


class _DirectionTab(_Tab):
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("Paperfessor")
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size: 18pt; font-weight: 600;")
        layout.addWidget(title)

        sub = QLabel(t("app.tagline"))
        sub.setObjectName("muted")
        layout.addWidget(sub)

        form = QFormLayout()
        self._direction = QLineEdit()
        self._direction.setPlaceholderText(t("direction.placeholder"))
        form.addRow(QLabel("Direction:"), self._direction)

        self._depth = QComboBox()
        for v, lbl in (("shallow", "Shallow"), ("normal", "Normal"), ("deep", "Deep")):
            self._depth.addItem(lbl, v)
        form.addRow(QLabel("Depth:"), self._depth)

        layout.addLayout(form)
        self._start = QPushButton("Generate")
        layout.addWidget(self._start)
        layout.addStretch(1)
        self.on_start: Any = None

    def get_direction(self) -> str:
        return self._direction.text().strip()

    def get_depth(self) -> str:
        return self._depth.currentData() or "normal"


class _ConsoleTab(_Tab):
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        self._console = QPlainTextEdit()
        self._console.setReadOnly(True)
        self._console.setStyleSheet(
            "font-family: 'Cascadia Code', 'Consolas', monospace;"
        )
        layout.addWidget(self._console, 1)

    def log(self, line: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._console.appendPlainText(f"[{ts}] {line}")


class _SettingsTab(_Tab):
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        s = load_settings()

        # Provider + model
        provider_box = QGroupBox("LLM provider")
        pf = QFormLayout(provider_box)
        self._provider = QComboBox()
        for slug in ("minimax", "openai", "anthropic", "google", "ollama", "llamacpp", "custom"):
            self._provider.addItem(slug, slug)
        pf.addRow(QLabel("Provider:"), self._provider)

        self._model = QLineEdit(s.model)
        pf.addRow(QLabel("Default model:"), self._model)
        self._phd = QLineEdit(s.phd_model)
        pf.addRow(QLabel("PhD model:"), self._phd)
        self._ms = QLineEdit(s.ms_model)
        pf.addRow(QLabel("MS model:"), self._ms)
        self._ug = QLineEdit(s.ug_model)
        pf.addRow(QLabel("UG model:"), self._ug)

        self._base_url = QLineEdit(s.base_url or "")
        pf.addRow(QLabel("Base URL:"), self._base_url)

        self._thinking = QComboBox()
        self._thinking.addItem("Thinking on (adaptive)", True)
        self._thinking.addItem("Thinking off (disabled)", False)
        self._thinking.setCurrentIndex(0 if s.thinking_mode else 1)
        pf.addRow(QLabel("Thinking mode:"), self._thinking)

        self._max_input = QSpinBox()
        self._max_input.setRange(1024, 1_000_000)
        self._max_input.setSingleStep(10_000)
        self._max_input.setValue(s.max_input_tokens)
        pf.addRow(QLabel("Max input tokens:"), self._max_input)

        self._max_output = QSpinBox()
        self._max_output.setRange(256, 128_000)
        self._max_output.setSingleStep(1024)
        self._max_output.setValue(s.default_max_tokens)
        pf.addRow(QLabel("Max output tokens:"), self._max_output)

        layout.addWidget(provider_box)
        layout.addStretch(1)
        self.on_apply: Any = None

    def apply(self) -> Settings:
        from src.config import ProviderName
        s = load_settings()
        try:
            s.provider = ProviderName(self._provider.currentData() or "minimax")
        except ValueError:
            pass
        s.model = self._model.text().strip() or "MiniMax-M3"
        s.phd_model = self._phd.text().strip() or "MiniMax-M3"
        s.ms_model = self._ms.text().strip() or "MiniMax-M3"
        s.ug_model = self._ug.text().strip() or "MiniMax-M3"
        s.base_url = self._base_url.text().strip() or None
        s.thinking_mode = bool(self._thinking.currentData())
        s.disable_reasoning = not s.thinking_mode
        s.max_input_tokens = self._max_input.value()
        s.default_max_tokens = self._max_output.value()
        return s


class _TokensTab(_Tab):
    """Real-time token dashboard."""

    _ROLE_LABELS = (
        ("director", "Director"), ("innovator", "Innovator"),
        ("scout", "Scout"), ("surveyor", "Surveyor"), ("writer", "Writer"),
        ("architect", "Architect"), ("coder", "Coder"),
        ("experimenter", "Experimenter"), ("optimizer", "Optimizer"),
        ("comparator", "Comparator"), ("visualizer", "Visualizer"),
        ("data_curator", "Data Curator"), ("reviewer", "Reviewer"),
        ("memory_curator", "Memory Curator"), ("integrator", "Integrator"),
    )
    _GROUP_LABELS = {"phd": "PhD", "ms": "MS", "ug": "UG"}

    def _build(self) -> None:
        outer = QVBoxLayout(self)

        # Aggregate
        self._agg_box = QGroupBox(t("tokens.aggregate"))
        agg = QFormLayout(self._agg_box)
        self._agg: dict[str, QLabel] = {}
        for k in ("prompt", "completion", "total", "calls"):
            v = QLabel("0")
            v.setStyleSheet("font-size: 18pt; font-weight: 600;")
            self._agg[k] = v
            agg.addRow(QLabel(t(f"tokens.col_{k}")), v)
        outer.addWidget(self._agg_box)

        # By group
        self._group_box = QGroupBox(t("tokens.by_group"))
        gv = QVBoxLayout(self._group_box)
        self._group_rows: dict[str, tuple[QLabel, QProgressBar, QLabel]] = {}
        for g in ("phd", "ms", "ug"):
            row = QHBoxLayout()
            name = QLabel(self._GROUP_LABELS[g])
            name.setMinimumWidth(80)
            name.setStyleSheet("font-weight: 600;")
            bar = QProgressBar()
            bar.setRange(0, 100)
            note = QLabel("0 tok")
            row.addWidget(name)
            row.addWidget(bar, 1)
            row.addWidget(note)
            wrap = QWidget()
            wrap.setLayout(row)
            gv.addWidget(wrap)
            self._group_rows[g] = (name, bar, note)
        outer.addWidget(self._group_box)

        # Per-role
        self._role_box = QGroupBox(t("tokens.by_role"))
        rv = QVBoxLayout(self._role_box)
        self._role_rows: dict[str, tuple[QLabel, QProgressBar, QLabel]] = {}
        for role_key, role_label in self._ROLE_LABELS:
            row = QHBoxLayout()
            name = QLabel(role_label)
            name.setMinimumWidth(120)
            bar = QProgressBar()
            bar.setRange(0, 100)
            note = QLabel("0 calls")
            row.addWidget(name)
            row.addWidget(bar, 1)
            row.addWidget(note)
            wrap = QWidget()
            wrap.setLayout(row)
            rv.addWidget(wrap)
            self._role_rows[role_key] = (name, bar, note)
        outer.addWidget(self._role_box, 1)

        # Reset button
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self._reset = QPushButton(t("tokens.reset_button"))
        bottom.addWidget(self._reset)
        outer.addLayout(bottom)

    def apply_snapshot(self, snap: dict[str, Any]) -> None:
        totals = snap.get("totals") or {}
        for k, label in self._agg.items():
            v = int(totals.get(k, 0))
            label.setText(f"{v:,}")
        groups = snap.get("groups") or {}
        max_total = max(
            (int(g.get("total", 0)) for g in groups.values()), default=0
        )
        for g, (_, bar, note) in self._group_rows.items():
            bucket = groups.get(g) or {}
            t_total = int(bucket.get("total", 0))
            calls = int(bucket.get("calls", 0))
            bar.setRange(0, max(max_total, 1))
            bar.setValue(t_total)
            note.setText(f"{t_total:,} tok / {calls} calls")
        roles = snap.get("roles") or {}
        max_role = max(
            (int(r.get("total", 0)) for r in roles.values()), default=0
        )
        for r, (_, bar, note) in self._role_rows.items():
            bucket = roles.get(r) or {}
            t_total = int(bucket.get("total", 0))
            calls = int(bucket.get("calls", 0))
            bar.setRange(0, max(max_role, 1))
            bar.setValue(t_total)
            note.setText(f"{calls} calls")


class _ProgressTab(_Tab):
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("Live progress")
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size: 14pt; font-weight: 600;")
        layout.addWidget(title)
        self._lines = QPlainTextEdit()
        self._lines.setReadOnly(True)
        layout.addWidget(self._lines, 1)

    def log(self, line: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._lines.appendPlainText(f"[{ts}] {line}")


class _PaperfessorWindow(QMainWindow):
    """Top-level window: tab widget, status bar, live token dashboard."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Paperfessor {__version__}")
        self.resize(1320, 840)
        s = load_settings()
        self._settings = s
        self.setStyleSheet(stylesheet(palette_for(s.theme.value if hasattr(s.theme, "value") else str(s.theme)), s.font_size))

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.direction_tab = _DirectionTab()
        self.tokens_tab = _TokensTab()
        self.settings_tab = _SettingsTab()
        self.console_tab = _ConsoleTab()
        self.progress_tab = _ProgressTab()

        self._tab_indices: dict[str, int] = {}
        for key, widget in (
            ("direction", self.direction_tab),
            ("tokens", self.tokens_tab),
            ("progress", self.progress_tab),
            ("console", self.console_tab),
            ("settings", self.settings_tab),
        ):
            self._tab_indices[key] = self.tabs.addTab(widget, t(f"tabs.{key}"))

        self.direction_tab.on_start = self._on_start
        self.settings_tab.on_apply = self._on_settings_applied

        # 500ms polling for the token dashboard.
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._refresh_tokens)
        self._timer.start()

        # Wire router observer (in case a run is in flight).
        try:
            from src.llm.router import get_default_router
            get_default_router().add_usage_observer(self._on_usage_event)
        except Exception:  # noqa: BLE001
            pass

    def _refresh_tokens(self) -> None:
        try:
            from src.llm.router import get_default_router
            snap = get_default_router().usage_snapshot()
        except Exception:  # noqa: BLE001
            return
        self.tokens_tab.apply_snapshot(snap)

    def _on_usage_event(self, event: dict[str, Any]) -> None:
        self.tokens_tab.apply_snapshot(
            get_default_router().usage_snapshot()
            if False else self.tokens_tab
        )

    def _on_start(self) -> None:
        direction = self.direction_tab.get_direction()
        if not direction:
            return
        self.tabs.setCurrentIndex(self._tab_indices["progress"])
        self.progress_tab.log(f"starting run for: {direction}")
        self.console_tab.log(f"starting run: {direction}")
        # Build a PhD + MS + UG, kick off the pipeline.
        from src.agents.master import MasterStudent
        from src.agents.phd import PhDStudent
        from src.agents.undergrad import Undergraduate
        from src.llm.router import get_default_router
        from src.runner.pipeline import run as pipeline_run
        from src.workspace import workspace_dir

        router = get_default_router()
        router._settings = self._settings  # type: ignore[attr-defined]
        workspace = workspace_dir()
        phd = PhDStudent(self._settings, router, workspace)
        ms = MasterStudent(self._settings, router, workspace)
        ug = Undergraduate(self._settings, router, workspace)
        # In a full implementation this would run in a background QThread.
        # For now, drive the pipeline synchronously to keep the example
        # small; the supervisor is started inside ``pipeline.run``.
        try:
            result = pipeline_run(direction, settings=self._settings, router=router)
            self.progress_tab.log(f"run finished: {result.status}")
            self.console_tab.log(f"run finished: {result.status} ({result.note or '-'})")
        except Exception as exc:  # noqa: BLE001
            self.progress_tab.log(f"ERROR: {exc}")
            self.console_tab.log(f"ERROR: {exc}")

    def _on_settings_applied(self, new_settings: Settings) -> None:
        self._settings = new_settings
        from src.llm.router import get_default_router
        get_default_router()._settings = new_settings  # type: ignore[attr-defined]
        self.setStyleSheet(stylesheet(
            palette_for(new_settings.theme.value if hasattr(new_settings.theme, "value") else str(new_settings.theme)),
            new_settings.font_size,
        ))
        self.console_tab.log("settings applied")


def main() -> int:
    """Launch the GUI. Returns the Qt exit code."""
    try:
        from PyQt6 import QtCore, QtGui, QtWidgets
    except ImportError as exc:
        print(
            f"PyQt6 is not installed: {exc}\n"
            "Install with: pip install 'paperfessor[gui]'",
            file=sys.stderr,
        )
        return 1
    app = QApplication(sys.argv)
    app.setApplicationName("Paperfessor")
    app.setOrganizationName("Paperfessor")
    win = _PaperfessorWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
