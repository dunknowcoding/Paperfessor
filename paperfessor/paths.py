"""User data directory helpers.

Centralizes all filesystem locations Paperfessor uses, so the rest
of the codebase never hardcodes ``~/.paperfessor`` or similar.

Workspace resolution order (cross-platform):

1. ``PAPERFESSOR_WORKSPACE`` environment variable, when set.
2. The current working directory, when it looks like a Paperfessor
   project checkout (has a ``workspace/`` or ``Skill/`` directory).
3. The per-user data directory from :mod:`platformdirs`
   (e.g. ``%LOCALAPPDATA%/Paperfessor`` on Windows,
   ``~/.local/share/Paperfessor`` on Linux,
   ``~/Library/Application Support/Paperfessor`` on macOS).

Layout under the workspace root:

    workspace/                  3-agent active workspace (runtime, gitignored)
        doc_memo.md
        article_memo.md
        shared/{research_guide,code_guide,research_log,code_log}.md
        paper/ ...
        src/ ...
        archived/ ...
        memory.sqlite3           long-term memory (SQLite)
"""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "Paperfessor"
APP_AUTHOR = "Paperfessor"


def data_dir() -> Path:
    """Per-user application data directory (platform-appropriate)."""
    return Path(user_data_dir(APP_NAME, APP_AUTHOR))


def workspace_root() -> Path:
    """The project root. Override via PAPERFESSOR_WORKSPACE."""
    env = os.environ.get("PAPERFESSOR_WORKSPACE")
    if env:
        return Path(env).expanduser().resolve()
    cwd = Path.cwd()
    if (cwd / "workspace").is_dir() or (cwd / "Skill").is_dir():
        return cwd.resolve()
    return data_dir()


def workspace_dir() -> Path:
    """The 3-agent workspace directory at the project root."""
    return workspace_root() / "workspace"


def memory_db_path() -> Path:
    """The long-term memory SQLite DB. Lives under the workspace
    because the whole workspace is gitignored runtime data.
    """
    return workspace_dir() / "memory.sqlite3"


def ensure_dirs() -> None:
    """Create the workspace dir if it doesn't already exist."""
    workspace_dir().mkdir(parents=True, exist_ok=True)


__all__ = [
    "APP_AUTHOR",
    "APP_NAME",
    "data_dir",
    "ensure_dirs",
    "memory_db_path",
    "workspace_dir",
    "workspace_root",
]
