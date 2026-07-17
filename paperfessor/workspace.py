"""Workspace bootstrap and lifecycle (single file, inlined templates).

The runtime ``workspace/`` directory lives at the project root
(:func:`src.paths.workspace_dir`). The templates below are inlined
as a dict so the package has no parallel directory tree to keep in
sync. The :func:`bootstrap_workspace` helper creates the directory
on demand.

The runtime layout is::

    workspace/
        doc_memo.md
        article_memo.md
        shared/
            research_guide.md    (PhD -> MS, read-only for MS)
            code_guide.md        (PhD -> UG, read-only for UG)
            research_log.md      (MS writes here)
            code_log.md          (UG writes here)
        paper/                  (PhD-managed paper artifacts)
        src/                    (UG-managed code + datasets)
        archived/               (permanent per-attempt history)
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)


# ---- Templates (inlined to avoid a parallel directory tree) ---------------


WORKSPACE_TEMPLATES: Final[dict[str, str]] = {
    "doc_memo.md": (
        "# doc_memo.md\n\n"
        "> PhD's private memory. Cleared when a new paper starts.\n\n"
        "## Format\n\n"
        "```\n"
        "### YYYY-MM-DD HH:MM | <user request summary>\n"
        "- Method designed: <name>\n"
        "- Stage: <one of the method's stages>\n"
        "- Undergrad summary: <what they did, how it went>\n"
        "- MS summary: <what they did, how it went>\n"
        "- Interaction w/ Undergrad: <what we did, did it work, what we learned>\n"
        "- Interaction w/ MS: <what we did, did it work, what we learned>\n"
        "- Stage goal achieved: yes / partial / no\n"
        "- Lessons: <bullet list>\n"
        "- Final user-goal achieved: yes / no (filled in after all stages close)\n"
        "```\n\n"
        "## Active run\n"
    ),
    "article_memo.md": (
        "# article_memo.md\n\n"
        "> PhD's paper-writing memory. Cleared when a new paper starts.\n\n"
        "## Active run\n"
    ),
    "shared/research_guide.md": (
        "# research_guide.md\n\n"
        "> PhD's task list for the master's student. **Read-only** for the MS.\n\n"
        "## Active tasks\n\n"
        "- [ ] (no tasks yet - PhD will populate after parsing the user's research direction)\n\n"
        "## PhD instructions to the MS\n\n"
        "- All checkbox items here are tasks **I** (the PhD) am assigning to you.\n"
        "- You may only **read** this file. Do not edit it; if you think a task is\n"
        "  wrong or complete, write your reasoning in `research_log.md` and the PhD\n"
        "  will decide.\n"
        "- When you finish a task, mark it `[done]` *in your log entry*, not in this\n"
        "  file. The PhD will check the box here after reviewing.\n"
        "- Voided tasks will be marked `[voided - reason]`; treat them as cancelled\n"
        "  and stop working on them.\n"
        "- New tasks are added at the bottom under a date heading.\n\n"
        "## History\n\n"
        "(Completed and voided tasks move here.)\n"
    ),
    "shared/code_guide.md": (
        "# code_guide.md\n\n"
        "> PhD's task list for the undergraduate. **Read-only** for the UG.\n\n"
        "## Active tasks\n\n"
        "- [ ] (no tasks yet - PhD will populate after parsing the user's research direction)\n\n"
        "## PhD instructions to the UG\n\n"
        "- All checkbox items here are tasks **I** (the PhD) am assigning to you.\n"
        "- You may only **read** this file. Do not edit it; report your progress in\n"
        "  `code_log.md`.\n"
        "- The PhD may **void** a task (you must stop working on it) or **add** a new\n"
        "  task (you must not skip it). The PhD will also tell you in chat when this\n"
        "  happens.\n"
        "- Code, datasets, tools, and test scripts go under `../src/`. Working\n"
        "  progress reports and final results go in `code_log.md`.\n\n"
        "## History\n\n"
        "(Completed and voided tasks move here.)\n"
    ),
    "shared/research_log.md": (
        "# research_log.md\n\n"
        "> Master's student writes here. Format: timestamp + report subject\n"
        "> + brief content. The PhD scans the most recent entries to assess\n"
        "> progress and decide on the next moves.\n\n"
        "## Log entries\n"
    ),
    "shared/code_log.md": (
        "# code_log.md\n\n"
        "> Undergraduate writes here. Format: timestamp + report subject +\n"
        "> brief content. The PhD scans the most recent entries to assess\n"
        "> progress and decide on the next moves.\n\n"
        "## Log entries\n"
    ),
    "paper/README.md": (
        "# paper/\n\n"
        "The PhD student's paper folder.\n"
    ),
    "src/README.md": (
        "# src/\n\n"
        "The undergraduate's coding folder (per the user spec). Contents:\n\n"
        "- `code/` - Python source for the project\n"
        "- `datasets/` - datasets downloaded + preprocessed\n"
        "- `tools/` - third-party tools and binaries\n"
        "- `tests/` - unit and integration tests\n\n"
        "Note: this is the UG's runtime workspace, not the framework's\n"
        "top-level Python package (which is also called `src/`).\n"
    ),
    "archived/README.md": (
        "# archived/\n\n"
        "Permanent, append-only database of completed (and failed) paper attempts.\n"
    ),
}


# ---- Public API ------------------------------------------------------------


def workspace_dir() -> Path:
    """The runtime workspace directory at the project root."""
    from paperfessor.paths import workspace_dir as _wd

    return _wd()


def bootstrap_workspace(target: Path | None = None, *, force: bool = False) -> Path:
    """Create or update the workspace at ``target`` from the inlined templates.

    Behaviour:
    - Missing dir: create it and write all 9 template files.
    - Empty dir: write all 9 template files.
    - Non-empty dir (no ``force``): keep existing files; only write
      templates whose target path is missing. This is the idempotent
      "merge" mode that survives partial bootstraps.
    - Non-empty dir (``force=True``): wipe the tree and re-apply all
      templates.
    """
    target = Path(target) if target is not None else workspace_dir()
    if target.exists() and any(target.iterdir()):
        if force:
            logger.info("workspace exists at %s; force-rebuilding", target)
            shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)
        else:
            logger.info("workspace exists at %s; merging missing templates", target)
    else:
        target.mkdir(parents=True, exist_ok=True)
    written = 0
    for relpath, content in WORKSPACE_TEMPLATES.items():
        path = target / relpath
        if path.exists() and not force:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written += 1
    logger.info(
        "workspace bootstrap at %s: %d new / %d total templates",
        target, written, len(WORKSPACE_TEMPLATES),
    )
    return target


def archive_workspace(target: Path | None = None, archive_dir: Path | None = None) -> Path:
    """Move an existing workspace into ``archive_dir``."""
    from paperfessor.paths import workspace_root

    target = Path(target) if target is not None else workspace_dir()
    archive_dir = Path(archive_dir) if archive_dir is not None else workspace_root() / "archived"
    if not target.exists():
        raise FileNotFoundError(f"workspace does not exist: {target}")
    archive_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = archive_dir / f"{ts}-{target.name}"
    shutil.move(str(target), str(dest))
    logger.info("workspace %s archived to %s", target, dest)
    return dest


__all__ = [
    "WORKSPACE_TEMPLATES",
    "archive_workspace",
    "bootstrap_workspace",
    "workspace_dir",
]
