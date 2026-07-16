"""User data directory helpers.

Centralizes all filesystem locations Paperfessor uses, so the rest
of the codebase never hardcodes ``~/.paperfessor`` or similar.

Layout under the project root:

    workspace/                  v0.4: 3-agent active workspace (runtime, gitignored)
        doc_memo.md
        article_memo.md
        shared/{research_guide,code_guide,research_log,code_log}.md
        paper/README.md
        src/README.md
        archived/README.md
        memory.sqlite3           v0.4: long-term memory (SQLite)
"""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "Paperfessor"
APP_AUTHOR = "Paperfessor"

# Default workspace root for the bundled-on-Windows install. Users can
# override via PAPERFESSOR_WORKSPACE.
_DEFAULT_WORKSPACE = Path("G:/Arduino/driver/Paperfessor")


def workspace_root() -> Path:
    """The project root. Override via PAPERFESSOR_WORKSPACE."""
    env = os.environ.get("PAPERFESSOR_WORKSPACE")
    if env:
        return Path(env).expanduser().resolve()
    if _DEFAULT_WORKSPACE.exists() or os.name == "nt":
        return _DEFAULT_WORKSPACE.resolve()
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
    "ensure_dirs",
    "memory_db_path",
    "workspace_dir",
    "workspace_root",
]
