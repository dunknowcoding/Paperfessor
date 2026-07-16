"""The PhD student agent.

Supervisor of the 3-agent society. Owns:
- ``doc_memo.md`` and ``article_memo.md`` (private memory, cleared on new paper)
- ``shared/research_guide.md`` and ``shared/code_guide.md`` (PhD-only writes)
- ``archived/`` (read-only lookup before designing a new method)

Status transitions: idle -> planning -> dispatching -> monitoring ->
(reviewing -> writing -> ...) -> idle.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, TYPE_CHECKING

from src.agents.base import _WorkspaceAgent
from src.agents.status import PhDStatus

if TYPE_CHECKING:
    from src.config import Settings
    from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)


@dataclass
class GuideTask:
    """One checkbox in a research/code guide."""

    text: str
    done: bool = False
    voided: bool = False
    void_reason: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class PhDStudent(_WorkspaceAgent):
    """The PhD-student agent."""

    def __init__(self, settings: "Settings", router: "LLMRouter", workspace: Path) -> None:
        super().__init__(settings, router, workspace, group="phd")
        self._status: PhDStatus = PhDStatus.IDLE
        self._current_method: str = ""

    # ---- Status API (the contract the user spec asked for) -----------

    def status(self) -> PhDStatus:
        return self._status

    def status_dict(self) -> dict[str, str]:
        return {"agent": "phd", "status": self._status.value, "method": self._current_method}

    def set_status(self, status: PhDStatus) -> None:
        with self._lock:
            self._status = status
        self._record_status(status.value)
        self._emit_status("phd", status.value)

    def api_status(self) -> dict[str, Any]:
        """JSON-friendly status snapshot for external consumers (CLI / GUI)."""
        return {
            "agent": "phd",
            "status": self._status.value,
            "method": self._current_method,
            "history_len": len(self._status_history),
        }

    # ---- Memo writes (spec-format, per req.txt) -----------------------

    # Memos must stay concise (req.txt: the memory must not exceed the
    # model context window). When a memo file grows past this size we
    # keep the header + the most recent entries and drop the rest.
    _MEMO_MAX_BYTES = 120_000
    _MEMO_KEEP_ENTRIES = 40

    def _compact_memo_if_needed(self, path: Path) -> None:
        try:
            if not path.is_file() or path.stat().st_size <= self._MEMO_MAX_BYTES:
                return
            text = path.read_text(encoding="utf-8")
            head, sep, rest = text.partition("\n### ")
            if not sep:
                return
            entries = ("### " + rest).split("\n### ")
            entries = ["### " + e if not e.startswith("### ") else e
                       for e in entries]
            kept = entries[-self._MEMO_KEEP_ENTRIES:]
            dropped = len(entries) - len(kept)
            compacted = (
                head.rstrip()
                + f"\n\n> ({dropped} older entries compacted on "
                + datetime.now().strftime("%Y-%m-%d %H:%M")
                + "; full history lives in the archive and the SQLite memory)\n\n"
                + "\n\n".join(kept)
                + "\n"
            )
            path.write_text(compacted, encoding="utf-8")
        except Exception:  # noqa: BLE001
            logger.exception("memo compaction failed; continuing")

    def append_doc_memo(
        self,
        *,
        ts: str | None = None,
        user_request: str = "",
        method: str = "",
        stage: str = "",
        ug_summary: str = "",
        ms_summary: str = "",
        interaction_ug: str = "",
        interaction_ms: str = "",
        stage_goal: str = "",
        lessons: str = "",
        final_goal: str = "",
        stage_complete: bool = False,
    ) -> None:
        """Append a doc_memo entry in the spec's required format.

        Format (per req.txt):
            日期时间 - 用户要求摘要 - 我设计的方法 - 该方法的阶段
            - 每个阶段本科生的表现总结
            - 研究生表现总结
            - 与本科生互动总结
            - 与硕士生互动总结
            - 该阶段是否实现目标，经验教训总结
            - 最终结果是否实现用户目标，是否成功
        """
        path = self._workspace / "doc_memo.md"
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text(self._doc_memo_header(), encoding="utf-8")
            with path.open("a", encoding="utf-8") as f:
                if path.stat().st_size == 0:
                    f.write(self._doc_memo_header())
                stamp = ts or datetime.now().strftime("%Y-%m-%d %H:%M")
                f.write(f"\n\n### {stamp}\n")
                f.write(f"- **User request**: {user_request or '(unspecified)'}\n")
                f.write(f"- **Method**: {method or '(none)'}\n")
                f.write(f"- **Stage**: {stage or '(unspecified)'}\n")
                f.write(f"- **UG summary**: {ug_summary or '(no UG activity)'}\n")
                f.write(f"- **MS summary**: {ms_summary or '(no MS activity)'}\n")
                f.write(f"- **UG interaction**: {interaction_ug or '-'}\n")
                f.write(f"- **MS interaction**: {interaction_ms or '-'}\n")
                f.write(f"- **Stage goal achieved**: {'yes' if stage_complete else 'no / partial'}\n")
                f.write(f"- **Lessons**: {lessons or '-'}\n")
                if final_goal:
                    f.write(f"- **Final user-goal**: {final_goal}\n")
            self._compact_memo_if_needed(path)

    def append_article_memo(
        self,
        *,
        ts: str | None = None,
        direction: str = "",
        method: str = "",
        progress: str = "",
        status: str = "",
        template_check: str = "",
        text_check: str = "",
        table_check: str = "",
        style_check: str = "",
        figure_check: str = "",
        references_check: str = "",
        other_check: str = "",
    ) -> None:
        """Append an article_memo entry in the spec's required format.

        Format (per req.txt):
            日期时间 - 论文研究方向 - 对应的方法
            - 论文进度 - 进展情况（代码/数据/理论/论证/图表/描述完整性和严谨度）
            - 模版检查
            - 论文预览文字检查
            - 论文预览表格检查
            - 文风审查
            - 论文预览图检查
            - 参考文献检查
            - 其他元素检查
        """
        path = self._workspace / "article_memo.md"
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text(self._article_memo_header(), encoding="utf-8")
            with path.open("a", encoding="utf-8") as f:
                if path.stat().st_size == 0:
                    f.write(self._article_memo_header())
                stamp = ts or datetime.now().strftime("%Y-%m-%d %H:%M")
                f.write(f"\n\n### {stamp}\n")
                f.write(f"- **Direction**: {direction or '(unspecified)'}\n")
                f.write(f"- **Method**: {method or '(unspecified)'}\n")
                f.write(f"- **Progress**: {progress or '-'}\n")
                f.write(f"- **Status**: {status or '-'}\n")
                f.write(f"- **进展 (代码/数据/理论/论证/图表/描述完整性和严谨度)**: {status or '-'}\n")
                f.write(f"- **Template check**: {template_check or 'pending'}\n")
                f.write(f"- **Text check**: {text_check or 'pending'}\n")
                f.write(f"- **Table check**: {table_check or 'pending'}\n")
                f.write(f"- **Style check**: {style_check or 'pending'}\n")
                f.write(f"- **Figure check**: {figure_check or 'pending'}\n")
                f.write(f"- **References check**: {references_check or 'pending'}\n")
                f.write(f"- **Other (footnote/heading/symbols/ToC)**: {other_check or 'pending'}\n")
            self._compact_memo_if_needed(path)

    def clear_memos(self) -> None:
        """Reset doc_memo + article_memo. Called on a new paper."""
        for name, header in (
            ("doc_memo.md", self._doc_memo_header()),
            ("article_memo.md", self._article_memo_header()),
        ):
            path = self._workspace / name
            with self._lock:
                path.write_text(header, encoding="utf-8")

    def _doc_memo_header(self) -> str:
        return (
            "# doc_memo.md\n\n"
            "> PhD's private memory. **Cleared when a new paper starts.**\n"
            "> One entry per stage; the format is the spec-required fields:\n"
            "> 时间 - 用户要求摘要 - 我设计的方法 - 阶段 - UG表现 - MS表现\n"
            "> - 与UG互动 - 与MS互动 - 阶段目标 - 经验教训 - 最终目标\n\n"
            "## Active run\n"
        )

    def _article_memo_header(self) -> str:
        return (
            "# article_memo.md\n\n"
            "> PhD's paper-writing memory. **Cleared when a new paper starts.**\n"
            "> Each entry has the spec-required fields:\n"
            "> 时间 - 研究方向 - 方法 - 论文进度 - 进展(代码/数据/理论/论证/图表/严谨度)\n"
            "> - 模版检查 - 文字检查 - 表格检查 - 文风审查 - 图检查 - 参考文献 - 其他\n\n"
            "## Active run\n"
        )

    # ---- Guide writes (PhD-only) -------------------------------------

    def update_research_guide(
        self, tasks: Iterable[GuideTask], *, mode: str = "replace"
    ) -> None:
        self._write_guide(filename="research_guide.md", audience="MS",
                          tasks=tasks, mode=mode)

    def update_code_guide(
        self, tasks: Iterable[GuideTask], *, mode: str = "replace"
    ) -> None:
        self._write_guide(filename="code_guide.md", audience="UG",
                          tasks=tasks, mode=mode)

    def _write_guide(
        self, *, filename: str, audience: str, tasks: Iterable[GuideTask], mode: str,
    ) -> None:
        path = self._workspace / "shared" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        tasks = list(tasks)
        with self._lock:
            existing_active, history = self._read_guide(path)
            if mode == "replace":
                for t in existing_active:
                    if t.done or t.voided:
                        history.append(t)
                new_active = list(tasks)
            else:
                existing_texts = {t.text.strip() for t in existing_active}
                new_active = list(existing_active)
                for t in tasks:
                    if t.text.strip() not in existing_texts:
                        new_active.append(t)
            final_active: list[GuideTask] = []
            for t in new_active:
                if t.done or t.voided:
                    history.append(t)
                else:
                    final_active.append(t)
            self._render_guide(path, audience, final_active, history)

    def _read_guide(self, path: Path) -> tuple[list[GuideTask], list[GuideTask]]:
        if not path.exists():
            return [], []
        active: list[GuideTask] = []
        history: list[GuideTask] = []
        section = "active"
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.rstrip()
            if line.startswith("## History"):
                section = "history"
                continue
            if line.startswith("## "):
                section = "active"
                continue
            m = re.match(r"^- \[( |x|~)\] (.+)$", line)
            if not m:
                continue
            mark, text = m.group(1), m.group(2)
            task = GuideTask(text=text, done=(mark == "x"), voided=(mark == "~"))
            (history if section == "history" else active).append(task)
        return active, history

    def _render_guide(
        self, path: Path, audience: str, active: list[GuideTask], history: list[GuideTask],
    ) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines: list[str] = [
            f"# {path.stem}.md", "",
            f"> PhD's task list for the {audience}. **Read-only** for the {audience}.",
            "", "## Active tasks", "",
        ]
        if not active:
            lines.append("- [ ] (no tasks yet)")
        for t in active:
            lines.append(f"- [ ] {t.text}")
        lines += ["", f"## History (auto-archived at {ts})", ""]
        if not history:
            lines.append("(none yet)")
        for t in history:
            mark = "x" if t.done else "~"
            extra = f" - {t.void_reason}" if t.voided else ""
            lines.append(f"- [{mark}] {t.text}{extra}")
        lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")

    # ---- Archived lookup ---------------------------------------------

    def list_archived(self) -> list[dict[str, str]]:
        """Read metadata.yaml from each archived/ entry.

        The PhD calls this *before* designing a new method to avoid
        retreading failed/successful approaches.
        """
        root = self._workspace / "archived"
        if not root.is_dir():
            return []
        out: list[dict[str, str]] = []
        for entry in sorted(root.iterdir()):
            meta = entry / "metadata.yaml"
            if not meta.is_file():
                continue
            try:
                import yaml
                with meta.open(encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except Exception:  # noqa: BLE001
                data = {}
            data["_path"] = str(entry)
            out.append(data)
        return out

    # ---- Worker control (void / add / assess) -------------------------
    #
    # Per the user spec (req.txt):
    #   博士生根据硕士生和本科生的进度/报告反馈决定是否勾选两个文件的
    #   条目, 更改当前项目, 作废当前任务, 增加新任务, 并且向硕士和
    #   本科生发出相应的指令（如作废任务-强制停止当前的工作，增加新
    #   任务-阻止智能体跳过该新任务，需要根据实际情况合理推断设计）。
    #   共享文件夹由多个智能体共用, 子文件shared/research_guide.md
    #   是博士生给硕士生设计的工作任务列表（复选框条目）,
    #   shared/code_guide.md 是博士生给本科生设计的当前编码任务列
    #   表（复选框条目）. 这两个文档本科生和硕士生都无法更改, 只能
    #   读取. shared/research_log.md 记录硕士生的反馈结果,
    #   shared/code_log.md 记录本科生的反馈结果, 以日期/时间戳+报告
    #   主题+简要内容为条目. 博士生在监督指导过程中扫描log的最新
    #   记录或者多个最近记录检查工作结果, 本科生和硕士生的工作状态
    #   并进行分析评估 - 当前任务有无实现任务目标, 工作状态如何,
    #   是否做错, 是否需要暂停, 是否需要停止, 是否需要做更多, 还有
    #   更多较为复杂的组合.

    _WORKER_MD: dict[str, str] = {
        "ms": "research_guide.md",
        "ug": "code_guide.md",
    }
    _WORKER_LOG: dict[str, str] = {
        "ms": "research_log.md",
        "ug": "code_log.md",
    }

    def _guide_path(self, worker: str) -> Path:
        return self._workspace / "shared" / self._WORKER_MD[worker]

    def _log_path(self, worker: str) -> Path:
        return self._workspace / "shared" / self._WORKER_LOG[worker]

    def void_task(self, worker: str, task_text: str, *, reason: str = "") -> int:
        """Force-stop ``worker``'s current task.

        Marks the task as ``~voided~`` in the worker's guide file
        (this is the "强制停止当前的工作" semantic). The MS/UG code
        must treat any task marked with ``~`` as no-op (skip it).
        Records the action in doc_memo.

        Returns the number of tasks voided (0 or 1; 0 if not found).
        """
        if worker not in self._WORKER_MD:
            raise ValueError(f"unknown worker: {worker}")
        path = self._guide_path(worker)
        if not path.is_file():
            return 0
        text = path.read_text(encoding="utf-8")
        new_lines: list[str] = []
        voided = 0
        in_active = True
        for line in text.splitlines():
            m = re.match(r"^- \[( |x|~)\] (.+)$", line)
            if in_active and m and task_text.strip() in m.group(2):
                line = f"- [~] {m.group(2)}" + (f"  <!-- voided: {reason} -->" if reason else "")
                voided += 1
            new_lines.append(line)
            if line.startswith("## History"):
                in_active = False
        path.write_text("\n".join(new_lines), encoding="utf-8")
        if voided:
            self.append_doc_memo(
                user_request=f"void task for {worker}",
                method="(supervision)",
                stage="task-control",
                ug_summary=(f"voided '{task_text}'" if worker == "ug" else "(n/a)"),
                ms_summary=(f"voided '{task_text}'" if worker == "ms" else "(n/a)"),
                interaction_ug=(f"UG: forced to stop '{task_text}' ({reason})" if worker == "ug" else ""),
                interaction_ms=(f"MS: forced to stop '{task_text}' ({reason})" if worker == "ms" else ""),
                stage_goal=f"stop {worker}'s '{task_text}' (reason: {reason or 'unspecified'})",
                stage_complete=True,
            )
        return voided

    def add_task(self, worker: str, task_text: str, *, block_skip: bool = True) -> None:
        """Add a new task to ``worker``'s guide.

        The task is appended to the active list. If ``block_skip`` is
        True, we add a note that the worker must NOT skip this task
        without explicit PhD approval. The MS/UG must read this and
        respect the block.

        Records the action in doc_memo.
        """
        if worker not in self._WORKER_MD:
            raise ValueError(f"unknown worker: {worker}")
        path = self._guide_path(worker)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        prefix = "[BLOCKED] " if block_skip else ""
        new_task_line = f"- [ ] {prefix}{task_text}"
        # Insert before "## History" if it exists, else append.
        if "## History" in text:
            text = text.replace("## History", f"{new_task_line}\n\n## History", 1)
        else:
            text += f"\n{new_task_line}\n"
        path.write_text(text, encoding="utf-8")
        self.append_doc_memo(
            user_request=f"add task for {worker}",
            method="(supervision)",
            stage="task-control",
            ug_summary=(f"new task: '{task_text}'" if worker == "ug" else "(n/a)"),
            ms_summary=(f"new task: '{task_text}'" if worker == "ms" else "(n/a)"),
            interaction_ug=(
                f"UG must do '{task_text}'; "
                f"{'skip is blocked' if block_skip else 'skip is allowed'}"
                if worker == "ug" else ""
            ),
            interaction_ms=(
                f"MS must do '{task_text}'; "
                f"{'skip is blocked' if block_skip else 'skip is allowed'}"
                if worker == "ms" else ""
            ),
            stage_goal=f"add new '{task_text}' for {worker} (block_skip={block_skip})",
            stage_complete=True,
        )

    def mark_task_done(self, worker: str, task_text: str) -> int:
        """Tick the ``[x]`` checkbox next to ``task_text``."""
        if worker not in self._WORKER_MD:
            raise ValueError(f"unknown worker: {worker}")
        path = self._guide_path(worker)
        if not path.is_file():
            return 0
        lines = path.read_text(encoding="utf-8").splitlines()
        marked = 0
        for i, line in enumerate(lines):
            m = re.match(r"^- \[( |x|~)\] (.+)$", line)
            if m and task_text.strip() in m.group(2):
                lines[i] = f"- [x] {m.group(2)}"
                marked += 1
        path.write_text("\n".join(lines), encoding="utf-8")
        return marked

    def assess_worker(self, worker: str, *, scan_lines: int = 10) -> dict[str, object]:
        """Scan the worker's log + status and return a recommendation.

        Per req.txt: 博士生在监督指导过程中扫描log的最新记录或者
        多个最近记录检查工作结果, 本科生和硕士生的工作状态并进行
        分析评估 - 当前任务有无实现任务目标, 工作状态如何, 是否
        做错, 是否需要暂停, 是否需要停止, 是否需要做更多, 还有更多
        较为复杂的组合.

        Returns a dict with: status, last_subject, last_content,
        recommendation (continue | add_more | pause | stop | done |
        error), reason.
        """
        if worker not in self._WORKER_LOG:
            raise ValueError(f"unknown worker: {worker}")
        log_path = self._log_path(worker)
        guide_path = self._guide_path(worker)
        result: dict[str, object] = {
            "worker": worker,
            "log_exists": log_path.is_file(),
            "guide_exists": guide_path.is_file(),
            "last_subject": "",
            "last_content": "",
            "active_tasks": 0,
            "done_tasks": 0,
            "voided_tasks": 0,
            "recommendation": "continue",
            "reason": "",
        }
        if log_path.is_file():
            # Parse the markdown log: each entry is "### TIMESTAMP | SUBJECT"
            text = log_path.read_text(encoding="utf-8")
            entries = re.findall(r"### ([^|]+) \| ([^\n]+)\n([\s\S]*?)(?=\n### |\Z)",
                                  text)
            if entries:
                ts, subj, body = entries[-1]
                result["last_subject"] = subj.strip()
                result["last_content"] = body.strip()[:500]
        if guide_path.is_file():
            for line in guide_path.read_text(encoding="utf-8").splitlines():
                m = re.match(r"^- \[( |x|~)\] (.+)$", line)
                if m:
                    if m.group(1) == " ":
                        result["active_tasks"] = int(result["active_tasks"]) + 1
                    elif m.group(1) == "x":
                        result["done_tasks"] = int(result["done_tasks"]) + 1
                    elif m.group(1) == "~":
                        result["voided_tasks"] = int(result["voided_tasks"]) + 1
        # Heuristic recommendation
        if int(result["done_tasks"]) > 0 and int(result["active_tasks"]) == 0:
            result["recommendation"] = "done"
            result["reason"] = "all tasks done"
        elif int(result["voided_tasks"]) >= 3:
            result["recommendation"] = "stop"
            result["reason"] = "too many voided tasks"
        elif int(result["active_tasks"]) > 0 and not result["last_subject"]:
            result["recommendation"] = "pause"
            result["reason"] = "active tasks but no report"
        elif not result["log_exists"] and int(result["active_tasks"]) > 0:
            result["recommendation"] = "add_more"
            result["reason"] = "no log yet for an active worker"
        else:
            result["recommendation"] = "continue"
            result["reason"] = "tasks active and reports coming in"
        # The PhD mirrors the worker's recommendation in its own
        # status so external observers (GUI / CLI) can see why a
        # worker is being paused or stopped.
        if result["recommendation"] == "stop":
            self.set_status(PhDStatus.STOPPED)
        elif result["recommendation"] == "pause":
            self.set_status(PhDStatus.MONITORING)
        return result

    def void_method_for_sota_failure(
        self, *, method: str, reason: str, attempts: int,
    ) -> None:
        """If ``attempts`` rounds failed to reach SOTA, void the method
        and clear the paper + (most of) the src tree per req.txt:
            "进行多轮改进后依然无法达SOTA, 则清空paper文件夹中内容和
            src中除了已经下载的工具和数据集之外的所有文件, 根据其
            他待测试的方法判断是否删除src中已经下载的工具和数据集."

        ``paper/body/`` is wiped (the failed paper is not worth
        shipping). ``src/code/`` is wiped (the failed code is not
        worth shipping). ``src/papers/`` (downloaded PDFs), 
        ``src/datasets/`` (downloaded data), and ``src/figures/`` are
        kept. ``src/templates/`` is also kept (LaTeX templates).
        The voided method is recorded in the SQLite archive so future
        runs skip it.
        """
        import shutil
        paper_dir = self._workspace / "paper" / "body"
        if paper_dir.is_dir():
            shutil.rmtree(paper_dir, ignore_errors=True)
        code_dir = self._workspace / "src" / "code"
        if code_dir.is_dir():
            shutil.rmtree(code_dir, ignore_errors=True)
        # Tool / dataset dirs are kept but logged.
        kept = []
        for name in ("papers", "datasets", "figures", "templates"):
            d = self._workspace / "src" / name
            if d.is_dir():
                kept.append(str(d.relative_to(self._workspace)))
        self.append_doc_memo(
            user_request=method,
            method=method,
            stage="sota-void",
            ug_summary="(no UG summary — paper/src wiped)",
            ms_summary="(no MS summary — paper/src wiped)",
            interaction_ug=(
                f"after {attempts} failed iterations of '{method}', "
                f"PhD voided the method"
            ),
            interaction_ms=(
                f"after {attempts} failed iterations of '{method}', "
                f"PhD voided the method"
            ),
            stage_goal="void the method (SOTA not reached)",
            final_goal=(
                f"method {method!r} voided after {attempts} rounds; "
                f"reason: {reason}; kept: {kept}"
            ),
            stage_complete=False,
        )
        # Persist to the SQLite archive so the next run skips it.
        try:
            self.record_archived(
                research_area="(unset)",
                research_direction=method,
                research_question=method,
                method=method,
                success=False,
                reason=f"SOTA not reached after {attempts} rounds: {reason}",
            )
        except Exception:  # noqa: BLE001
            logger.exception("could not record voided method to archive")

    def archive_attempt(
        self,
        *,
        research_area: str,
        research_direction: str,
        research_question: str,
        method: str,
        success: bool,
        reason: str,
        paper_zip: Path | None,
    ) -> Path:
        """Move a finished attempt to ``archived/`` with metadata.

        Per the spec (req.txt): "zip文件只存储pa" — the zip we
        archive must contain *only* the paper PDF. The function
        also writes a ``metadata.yaml`` with the spec-required
        fields (research_area, research_direction,
        research_question, method, success, reason, paper_result).

        Returns the archive directory path.
        """
        import shutil
        import zipfile
        import yaml

        status = "success" if success else "failed"
        # Spec: 关键字 = 研究领域-研究方向-研究问题-博士生提出的方法-该方法的是否成功
        slug = (
            f"{_slugify(research_area)}-{_slugify(research_direction)}-"
            f"{_slugify(research_question)}-{_slugify(method)}-{status}"
        )
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self._workspace / "archived" / slug / run_id
        target.mkdir(parents=True, exist_ok=True)
        # Build the spec-required zip: PDF only.
        zip_path = target / f"paper-{run_id}.zip"
        if paper_zip is not None and paper_zip.is_file():
            zip_src = paper_zip
        else:
            # If no zip passed, look for the rendered PDF.
            candidate = self._workspace / "paper" / "body" / "paper.pdf"
            zip_src = candidate if candidate.is_file() else None
        if zip_src is not None and zip_src.is_file() and zip_src.suffix.lower() == ".pdf":
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                # The user spec: "zip file only stores paper.pdf".
                zf.write(zip_src, arcname=zip_src.name)
        else:
            # Caller passed a non-PDF (the .md fallback) or the
            # PDF does not exist. Do NOT create the zip at all;
            # the metadata's paper_result will read
            # "(no PDF; build failed)".
            zip_path = None
        meta = {
            "research_area": research_area,
            "research_direction": research_direction,
            "research_question": research_question,
            "method": method,
            "success": success,
            "reason": reason,
            "paper_result": (
                str(zip_path.relative_to(self._workspace))
                if zip_path is not None else "(no PDF; build failed)"
            ),
            "archived_at": datetime.now().isoformat(timespec="seconds"),
            "run_id": run_id,
        }
        with (target / "metadata.yaml").open("w", encoding="utf-8") as f:
            yaml.safe_dump(meta, f, allow_unicode=True, sort_keys=False)
        return target

    # ---- Venue template orchestration -----------------------------------

    def detect_and_fetch_venue(self, direction: str) -> dict[str, object]:
        """Pick the right target venue for ``direction`` and try to
        download its official template.

        The PhD's LLM does the *design* decision: it reads the user
        direction plus the catalogue of known venues and chooses the
        single best home for the paper. The PhD then downloads the
        chosen template (or falls back to acmart if the download
        fails). The LLM is the designer; this method is the
        orchestrator that calls the LLM and executes the result.
        """
        from src.research.venues import (
            _VENUE_TEMPLATES,
            download_venue_template,
            venue_label,
        )
        from src.research.sources.venue_index import (
            primary_venue_for_direction,
        )

        # 1. Catalogue of known venues, formatted for the LLM prompt.
        catalogue_lines: list[str] = []
        for vid, tpl in _VENUE_TEMPLATES.items():
            catalogue_lines.append(
                f"- id={vid} name={tpl.venue_name!r} ({tpl.venue_full}); "
                f"class={tpl.class_name}; page_limit={tpl.page_limit}"
            )
        catalogue = "\n".join(catalogue_lines)
        # Honour a user override: if the direction names a venue,
        # use it directly without bothering the LLM.
        override_match = None
        d_lower = direction.lower()
        for vname in (
            "neurips", "icml", "iclr", "cvpr", "iccv", "eccv",
            "acl", "emnlp", "naacl", "kdd", "aaai", "ijcai",
            "uai", "aistats", "icra", "iros",
        ):
            if vname in d_lower:
                override_match = vname
                break

        # 2. Ask the PhD's LLM to pick a venue. The LLM is the
        #    designer; we only pass it the data and the rules.
        #    We retry up to 3 times because the LLM is sometimes flaky
        #    on long structured-output prompts.
        picked_id = ""
        raw = ""
        if override_match is None:
            sys_prompt = (
                "You are a research PhD choosing the SINGLE best target "
                "venue for a new paper. The venue must be the canonical "
                "home for the topic, not just 'any top venue'. Use these "
                "rules:\n"
                "  - data mining / time series / anomaly / outlier / fraud / "
                "sensor / forecasting / iot / wearable -> KDD\n"
                "  - NLP / language / text / llm / translation / dialogue / "
                "question answering / summarization / speech -> ACL (or EMNLP)\n"
                "  - computer vision / image / object detection / segmentation / "
                "3d / video / face -> CVPR (or ICCV/ECCV)\n"
                "  - reinforcement learning / agent / policy -> NeurIPS or ICML\n"
                "  - robotics / manipulation / locomotion / grasping -> ICRA (or IROS)\n"
                "  - general machine learning / method paper / theory -> NeurIPS (or ICML/ICLR)\n"
                "  - graph / network / knowledge graph -> KDD (or WWW)\n"
                "  - bayesian / statistical -> AISTATS (or UAI)\n"
                "Output a single line: `VENUE_ID: <id>` where <id> is from "
                "the catalogue below. No prose, no explanation, no "
                "markdown. Just the VENUE_ID line."
            )
            user_prompt = (
                f"Research direction: {direction!r}\n\n"
                f"Catalogue of known venues:\n{catalogue}\n\n"
                f"Pick the venue. Output: `VENUE_ID: <id>`"
            )
            for attempt in range(3):
                raw = self.call_llm(
                    role="innovator",
                    system=sys_prompt,
                    user=user_prompt,
                    max_tokens=60,
                    temperature=0.0,
                )
                picked_id = _parse_venue_id(raw) or ""
                if picked_id:
                    break
        else:
            # Reverse-lookup the id from the override name.
            from src.research.sources.venue_index import (
                NEURIPS_S, ICML_S, ICLR_S, CVPR_S, ICCV_S, ECCV_S,
                ACL_S, EMNLP_S, NAACL_S, KDD_S, AAAI_S, IJCAI_S,
                UAI_S, AISTATS_S, ICRA_S, IROS_S,
            )
            name_to_id = {
                "neurips": NEURIPS_S, "icml": ICML_S, "iclr": ICLR_S,
                "cvpr": CVPR_S, "iccv": ICCV_S, "eccv": ECCV_S,
                "acl": ACL_S, "emnlp": EMNLP_S, "naacl": NAACL_S,
                "kdd": KDD_S, "aaai": AAAI_S, "ijcai": IJCAI_S,
                "uai": UAI_S, "aistats": AISTATS_S,
                "icra": ICRA_S, "iros": IROS_S,
            }
            picked_id = name_to_id[override_match]

        # 3. If the LLM did not pick a known venue, fall back to the
        #    deterministic keyword check (which is the same logic
        #    the LLM would have used had it been working).
        if picked_id not in _VENUE_TEMPLATES:
            picked_id = primary_venue_for_direction(direction)
            if picked_id not in _VENUE_TEMPLATES:
                picked_id = "s4210195363"  # NeurIPS default

        template = _VENUE_TEMPLATES[picked_id]
        templates_dir = self._workspace / "paper" / "templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        downloaded = download_venue_template(template, templates_dir)
        class_name = template.class_name if downloaded else template.fallback_class
        class_source = "downloaded" if downloaded else "fallback"
        result: dict[str, object] = {
            "venue_id": template.venue_id,
            "venue_name": template.venue_name,
            "venue_full": template.venue_full,
            "class_name": class_name,
            "class_source": class_source,
            "template_path": str(downloaded) if downloaded else None,
            "page_limit": template.page_limit,
            "llm_decided": bool(override_match is None),
        }
        self._last_venue_choice = result
        return result

    # ---- Long-term memory (SQLite, v0.4) -----------------------------
    # The PhD is the only agent with direct access to the memory DB.
    # The MS and UG observe the workspace, but they do not write
    # history rows — the PhD decides what is and isn't a run.

    def record_run(
        self,
        *,
        direction: str,
        method: str,
        started_at: "datetime | None" = None,
        finished_at: "datetime | None" = None,
        status: str = "ok",
        paper_path: Path | None = None,
        note: str = "",
        config: dict | None = None,
    ) -> int:
        """Record a run row in the SQLite memory. Returns the row id.

        The PhD calls this at the end of every pipeline.run().
        """
        from datetime import datetime as _dt
        from src.memory import record_run as _record

        return _record(
            direction=direction,
            method=method,
            started_at=started_at or _dt.now(),
            finished_at=finished_at or _dt.now(),
            status=status,
            paper_path=str(paper_path) if paper_path else None,
            note=note,
            config=config,
        )

    def record_archived(
        self,
        *,
        research_area: str,
        research_direction: str,
        research_question: str,
        method: str,
        success: bool,
        reason: str = "",
        paper_path: Path | None = None,
        run_id: int | None = None,
    ) -> int:
        """Record an archived-attempt row in SQLite.

        Mirror of the YAML on disk. Use :meth:`lookup_method` to query.
        """
        from src.memory import record_archived as _record

        return _record(
            research_area=research_area,
            research_direction=research_direction,
            research_question=research_question,
            method=method,
            success=success,
            reason=reason,
            paper_path=str(paper_path) if paper_path else None,
            run_id=run_id,
        )

    def list_runs(self, limit: int = 50) -> list[dict]:
        """Read run history. The PhD uses this to spot prior attempts."""
        from src.memory import list_runs as _list

        return _list(limit=limit)

    def lookup_method(
        self, *, research_area: str, method: str, success_only: bool = True
    ) -> dict | None:
        """Look up a prior attempt at ``method``.

        Returns the most-recent archived row, or None if no prior
        attempt was made. The PhD uses this to skip methods that have
        already succeeded or that were vetoed.
        """
        from src.memory import lookup_method as _lookup

        return _lookup(
            research_area=research_area, method=method, success_only=success_only
        )

    def list_archived_db(self, limit: int = 100) -> list[dict]:
        """List all archived attempts from the DB (most-recent first)."""
        from src.memory import list_archived as _list

        return _list(limit=limit)

    def memory_stats(self) -> dict:
        """Aggregate counts (runs / runs_ok / archived)."""
        from src.memory import stats as _stats

        return _stats()


def _slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "unknown"


def _parse_venue_id(text: str) -> str | None:
    """Pull ``s4210xxxxxx`` from an LLM reply like ``VENUE_ID: s4210195363``.

    The LLM sometimes truncates the id or pads it. We accept any
    ``s\\d+`` and look it up against the catalogue. If the LLM gave
    a partial id that uniquely matches a known venue, we use it.
    """
    if not text:
        return None
    # Try the canonical "VENUE_ID: <id>" form.
    m = re.search(r"VENUE_ID\s*[:=]\s*(s\d+)", text, re.IGNORECASE)
    if m:
        return _match_known(m.group(1))
    # Any s-prefixed token in the reply.
    m = re.search(r"\b(s\d+)\b", text)
    if m:
        return _match_known(m.group(1))
    return None


def _match_known(sid: str) -> str | None:
    """Look up ``sid`` in the venue catalogue, allowing partial matches."""
    from src.research.venues import _VENUE_TEMPLATES
    if sid in _VENUE_TEMPLATES:
        return sid
    # Partial match: find a known id that starts with ``sid``.
    candidates = [k for k in _VENUE_TEMPLATES if k.startswith(sid) or sid.startswith(k)]
    if len(candidates) == 1:
        return candidates[0]
    return None


__all__ = ["GuideTask", "PhDStudent"]
