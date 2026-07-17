"""The undergraduate agent.

Coding, testing, dataset handling, and figure capture. Read-only
access to ``shared/code_guide.md``; write-only access to
``shared/code_log.md``.

The UG also has a ``screenshot`` capability: it can render a PDF
page to a PNG (via :mod:`src.research.web`) and save the figure
into ``workspace/src/figures/`` for the MS agent or the paper to
use. The MS agent owns the high-level ``screenshot_figure`` API;
the UG re-exposes a thin wrapper that the code phase uses after
running a benchmark to capture a training-curve figure.

Status enum: coding <-> thinking -> reporting -> idle.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from paperfessor.agents.base import _WorkspaceAgent
from paperfessor.agents.phd import GuideTask
from paperfessor.agents.status import UndergradStatus

if TYPE_CHECKING:
    from paperfessor.config import Settings
    from paperfessor.llm.router import LLMRouter


logger = logging.getLogger(__name__)


class Undergraduate(_WorkspaceAgent):
    """The undergraduate agent."""

    def __init__(self, settings: "Settings", router: "LLMRouter", workspace: Path) -> None:
        super().__init__(settings, router, workspace, group="ug")
        self._status: UndergradStatus = UndergradStatus.IDLE

    # ---- Status API ----------------------------------------------------

    def status(self) -> UndergradStatus:
        return self._status

    def status_dict(self) -> dict[str, str]:
        return {"agent": "ug", "status": self._status.value}

    def set_status(self, status: UndergradStatus) -> None:
        with self._lock:
            self._status = status
        self._record_status(status.value)
        self._emit_status("ug", status.value)

    def api_status(self) -> dict[str, Any]:
        """JSON-friendly status snapshot for external consumers (CLI / GUI)."""
        return {
            "agent": "ug",
            "status": self._status.value,
            "history_len": len(self._status_history),
        }

    # ---- Guide read (read-only) ----------------------------------------

    def read_code_guide(self) -> list[GuideTask]:
        path = self._workspace / "shared" / "code_guide.md"
        if not path.exists():
            return []
        tasks: list[GuideTask] = []
        in_active = True
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.rstrip()
            if line.startswith("## History"):
                in_active = False
                continue
            if line.startswith("## "):
                in_active = True
                continue
            if not in_active:
                continue
            m = re.match(r"^- \[( |x|~)\] (.+)$", line)
            if not m:
                continue
            mark, text = m.group(1), m.group(2)
            tasks.append(GuideTask(text=text, done=(mark == "x"), voided=(mark == "~")))
        return tasks

    # ---- Log write -----------------------------------------------------

    def write_code_log(
        self,
        *,
        subject: str,
        content: str,
        task_ref: str | None = None,
    ) -> None:
        """Append an entry to ``shared/code_log.md``."""
        path = self._workspace / "shared" / "code_log.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = f"### {ts} | {subject}"
        if task_ref:
            header += f" | task: {task_ref}"
        with self._lock:
            with path.open("a", encoding="utf-8") as f:
                if path.stat().st_size == 0:
                    f.write("# code_log.md\n\n> UG's reports.\n\n## Log entries\n")
                f.write(f"\n{header}\n{content.strip()}\n")

    # ---- Code + screenshot ---------------------------------------------

    def run_python(self, script: str, *, cwd: Path | None = None,
                    timeout: float = 60.0) -> tuple[int, str, str]:
        """Run a Python script and return (returncode, stdout, stderr).

        The UG uses this for smoke tests on the code it writes. If
        the script exits non-zero, the caller is expected to surface
        the error in the code log.
        """
        self.set_status(UndergradStatus.CODING)
        try:
            proc = subprocess.run(
                [sys.executable, "-c", script],
                cwd=str(cwd) if cwd else None,
                capture_output=True, text=True, timeout=timeout,
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            return 124, exc.stdout or "", f"timeout after {timeout}s"
        except Exception as exc:  # noqa: BLE001
            return 1, "", f"runner error: {exc}"

    def screenshot(self, pdf_path: Path, page_num: int, out_path: Path | None = None) -> Path:
        """Capture a page of a PDF as a PNG.

        Thin wrapper over :func:`src.research.web.screenshot_pdf_page`.
        Used by the UG to capture training curves, architecture
        diagrams, and other figures for the paper. Output defaults
        to ``workspace/src/figures/<pdf-stem>/page_NNNN.png``.
        """
        self.set_status(UndergradStatus.CODING)
        from paperfessor.research import web as web_tools
        if out_path is None:
            out_path = self._workspace / "src" / "figures" / pdf_path.stem / f"page_{page_num:04d}.png"
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        return web_tools.screenshot_pdf_page(pdf_path, page_num, out_path)

    def screenshot_url(self, url: str, out_path: Path) -> Path:
        """Capture a webpage as a PNG.

        Used when the UG needs to archive a figure from a lab site
        or supplementary webpage. Returns the path to the saved PNG.
        """
        self.set_status(UndergradStatus.CODING)
        from paperfessor.research import web as web_tools
        return web_tools.screenshot_url(url, out_path)

    # ---- LLM call (UG-flavored prompt) ---------------------------------

    def ask(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        return self.call_llm(role="coder", system=system, user=user, max_tokens=max_tokens)

    # ---- Toolbelt (permission-gated; every use logged) ------------------
    #
    # Artifact organization rules (enforced by these helpers):
    #   src/code/     final scripts + models        (cleared per run)
    #   src/tmp/      temporary/scratch scripts     (cleared per run)
    #   src/datasets/ downloaded data + manifests   (persistent)
    #   src/tools/    installed tools + install log (persistent)
    #   src/results/  experiment outputs            (cleared per run)
    #   src/figures/  rendered figures              (cleared per run)
    # All paths the toolbelt touches MUST resolve inside workspace/src.

    def _src_path(self, rel: str) -> Path:
        """Resolve ``rel`` inside workspace/src; refuse escapes."""
        base = (self._workspace / "src").resolve()
        p = (base / rel).resolve()
        if base not in p.parents and p != base:
            raise PermissionError(f"path escapes workspace/src: {rel!r}")
        return p

    def _permitted(self, flag: str) -> bool:
        return bool(getattr(self._settings, flag, True))

    def run_tool(self, argv: list[str], *, cwd: str = "",
                 timeout: float | None = None) -> tuple[int, str, str]:
        """Run a local CLI tool (matlab -batch, Rscript, plotting or
        office CLIs, converters, test runners, ...) inside the
        workspace. No shell interpretation (argv list, shell=False);
        gated by ``ug_allow_local_tools``; every invocation is logged
        to code_log.md with its exit code."""
        if not self._permitted("ug_allow_local_tools"):
            raise PermissionError("local tools disabled (ug_allow_local_tools=false)")
        if not argv or not isinstance(argv, (list, tuple)):
            raise ValueError("argv must be a non-empty list")
        timeout = timeout or float(
            getattr(self._settings, "ug_tool_timeout_seconds", 300))
        workdir = self._src_path(cwd) if cwd else (self._workspace / "src")
        self.set_status(UndergradStatus.CODING)
        try:
            proc = subprocess.run(
                list(argv), cwd=str(workdir), capture_output=True,
                text=True, timeout=timeout,
            )
            rc, out, err = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            rc, out, err = 124, exc.stdout or "", f"timeout after {timeout}s"
        except FileNotFoundError:
            rc, out, err = 127, "", f"tool not found: {argv[0]}"
        self.write_code_log(
            subject=f"tool: {argv[0]} (exit {rc})",
            content=f"argv: {argv}\ncwd: {workdir.name}\n"
                    f"stdout tail: {out[-400:]}\nstderr tail: {err[-400:]}",
            task_ref="tool",
        )
        return rc, out, err

    def pip_install(self, packages: list[str],
                    *, timeout: float = 600.0) -> bool:
        """Install Python packages (gated by ``ug_allow_installs``).
        Every install is appended to src/tools/installed.txt so the
        environment stays reproducible and auditable."""
        if not self._permitted("ug_allow_installs"):
            raise PermissionError("installs disabled (ug_allow_installs=false)")
        pkgs = [p for p in packages if re.match(r"^[A-Za-z0-9_.\-\[\]=<>!,]+$", p)]
        if not pkgs:
            return False
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", *pkgs],
            capture_output=True, text=True, timeout=timeout,
        )
        ok = proc.returncode == 0
        tools_dir = self._src_path("tools")
        tools_dir.mkdir(parents=True, exist_ok=True)
        with (tools_dir / "installed.txt").open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} "
                    f"{'OK' if ok else 'FAIL'} {' '.join(pkgs)}\n")
        self.write_code_log(
            subject=f"pip install {'ok' if ok else 'FAILED'}",
            content=f"packages: {pkgs}\n{(proc.stderr or '')[-400:]}",
            task_ref="install",
        )
        return ok

    def save_script(self, name: str, content: str,
                    *, temporary: bool = False) -> Path:
        """Save a script under the organization rules: final scripts
        to src/code/, scratch to src/tmp/ (cleared each run)."""
        sub = "tmp" if temporary else "code"
        path = self._src_path(f"{sub}/{Path(name).name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def read_own_code(self, rel: str) -> str:
        """Inspect a file the UG previously produced (src-scoped)."""
        return self._src_path(rel).read_text(encoding="utf-8")

    def run_tests(self, rel: str = "code",
                  *, timeout: float = 300.0) -> tuple[int, str]:
        """Run pytest over a src-scoped path; report to code_log."""
        target = self._src_path(rel)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(target), "-q"],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(self._workspace / "src"),
        )
        self.write_code_log(
            subject=f"tests on {rel} (exit {proc.returncode})",
            content=(proc.stdout or "")[-600:],
            task_ref="tests",
        )
        return proc.returncode, proc.stdout

    def make_zip(self, rel_paths: list[str], out_name: str) -> Path:
        """Zip src-scoped files into src/results/<out_name>."""
        import zipfile
        out = self._src_path(f"results/{Path(out_name).name}")
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for rel in rel_paths:
                p = self._src_path(rel)
                if p.is_file():
                    zf.write(p, arcname=p.name)
        return out

    # ---- Datasets (real download + preprocess) -------------------------

    def download_and_preprocess(self, name: str) -> dict[str, object]:
        """Fetch + preprocess ``name`` into ``workspace/src/datasets/``.

        The user spec (req.txt) says the UG must "下载了数据集后需要自
        己进行处理". This wraps :func:`src.research.datasets.fetch`,
        which handles download, SHA-256 hashing, deterministic
        train/val/test splits, and a manifest the paper can cite.

        Returns a small dict the UG logs to code_log.md. The PhD
        also reads the same manifest for the paper's Experimental
        Setup.
        """
        self.set_status(UndergradStatus.CODING)
        from paperfessor.research import datasets
        try:
            info = datasets.fetch(name, self._workspace)
        except Exception as exc:  # noqa: BLE001
            self.set_status(UndergradStatus.REPORTING)
            self.write_code_log(
                subject=f"download + preprocess '{name}' FAILED",
                content=f"error: {exc}",
            )
            self.set_status(UndergradStatus.IDLE)
            raise
        # Write the manifest into code_log.md so the PhD and the
        # paper can both see it.
        manifest = info.processed_files.get("manifest")
        manifest_text = manifest.read_text(encoding="utf-8") if manifest else "(no manifest)"
        self.write_code_log(
            subject=f"download + preprocess '{name}'",
            content=(
                f"path: {info.path.relative_to(self._workspace)}\n"
                f"sha256: {info.sha256}\n"
                f"size: {info.size_bytes} bytes\n"
                f"license: {info.license}\n"
                f"source: {info.source_url}\n\n"
                f"manifest:\n```\n{manifest_text}\n```\n\n"
                f"raw files: {[p.name for p in info.raw_files.values()]}\n"
                f"processed files: {[p.name for p in info.processed_files.values()]}\n"
            ),
        )
        self.set_status(UndergradStatus.IDLE)
        return {
            "name": info.name,
            "path": str(info.path),
            "sha256": info.sha256,
            "size_bytes": info.size_bytes,
            "license": info.license,
            "source_url": info.source_url,
        }

    def list_known_datasets(self) -> list[str]:
        from paperfessor.research.datasets import list_known
        return list_known()

    def clean(self) -> None:
        """Wipe UG-owned code/figures between runs while keeping
        datasets and downloaded papers (they are versioned by hash
        and reusable across runs). Mirrors the PhD's
        ``void_method_for_sota_failure`` reset for the UG side.
        """
        import shutil
        for sub in ("code", "figures"):
            d = self._workspace / "src" / sub
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)


__all__ = ["Undergraduate"]
