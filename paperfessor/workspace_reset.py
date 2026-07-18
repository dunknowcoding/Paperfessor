"""Workspace reset helpers.

Two reset levels are supported:

- ``prepare_workspace_for_new_paper``: clear the active paper state,
  memos, guides, and worker logs while preserving historical archive,
  downloaded datasets, tools, and the SQLite memory DB.
- ``hard_reset_workspace``: wipe the entire runtime workspace and
  rebuild it from templates. This clears archived attempts and the
  SQLite memory DB too.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Final

from paperfessor.workspace import WORKSPACE_TEMPLATES, bootstrap_workspace, workspace_dir


_RESET_TEMPLATE_PATHS: Final[tuple[str, ...]] = (
    "doc_memo.md",
    "article_memo.md",
    "shared/research_guide.md",
    "shared/code_guide.md",
    "shared/research_log.md",
    "shared/code_log.md",
)
_PAPER_KEEP: Final[set[str]] = {"README.md", "templates"}
# ``papers`` (downloaded PDFs) are kept across runs: they are keyed
# by arXiv id / DOI and re-downloading them every run wastes time
# and arXiv rate budget. code/figures/results are per-run artifacts
# and are cleared.
_SRC_KEEP: Final[set[str]] = {"README.md", "datasets", "tools", "papers"}


def prepare_workspace_for_new_paper(target: Path | None = None) -> Path:
    """Reset the active paper state while preserving durable assets."""
    target = Path(target) if target is not None else workspace_dir()
    bootstrap_workspace(target)
    _rewrite_from_templates(target, _RESET_TEMPLATE_PATHS)
    _clear_children(target / "paper", keep_names=_PAPER_KEEP)
    _clear_children(target / "src", keep_names=_SRC_KEEP)
    (target / "paper" / "body").mkdir(parents=True, exist_ok=True)
    return target


def reset_for_replan(target: Path | None = None) -> Path:
    """Reset for a fresh planning phase after all feasible methods on a
    direction have failed — WITHOUT losing accumulated memory.

    Per the spec: when the PhD exhausts its planned directions it
    starts a new planning phase but KEEPS its memory files (doc_memo,
    article_memo, the archive, the SQLite history) so the new plan is
    informed by everything learned. Only the generated article and the
    experiment artifacts — including downloaded datasets — are cleared.
    Downloaded PAPERS are kept (they are literature, not experiment
    output, and re-fetching wastes arXiv budget).
    """
    target = Path(target) if target is not None else workspace_dir()
    bootstrap_workspace(target)
    # Clear the generated article and experiment outputs, plus the
    # downloaded datasets — but NOT the memos/archive (durable memory)
    # and NOT src/papers/src/tools.
    _clear_children(target / "paper", keep_names=_PAPER_KEEP)
    _clear_children(target / "src", keep_names={"README.md", "papers", "tools"})
    # Reset only the active guides/logs; memos and archive persist.
    _rewrite_from_templates(target, (
        "shared/research_guide.md", "shared/code_guide.md",
        "shared/research_log.md", "shared/code_log.md",
    ))
    (target / "paper" / "body").mkdir(parents=True, exist_ok=True)
    return target


def hard_reset_workspace(target: Path | None = None) -> Path:
    """Wipe and rebuild the runtime workspace from templates."""
    target = Path(target) if target is not None else workspace_dir()
    return bootstrap_workspace(target, force=True)


def _rewrite_from_templates(target: Path, relpaths: tuple[str, ...]) -> None:
    for relpath in relpaths:
        path = target / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(WORKSPACE_TEMPLATES[relpath], encoding="utf-8")


def _clear_children(root: Path, *, keep_names: set[str]) -> None:
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
        return
    for child in root.iterdir():
        if child.name in keep_names:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


__all__ = [
    "hard_reset_workspace",
    "prepare_workspace_for_new_paper",
    "reset_for_replan",
]