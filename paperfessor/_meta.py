"""Paperfessor build metadata.

If an optional governance file (``SOUL.md``) is present at the project
root, the orchestrator hashes it at run start as an integrity check;
when absent (the normal case for an installed package) the check is
skipped gracefully.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

__version__: str = "1.3.0"
__author__: str = "Paperfessor Project"
__license__: str = "MIT"

# Path to the SOUL.md at the project root.
SOUL_PATH: Path = Path(__file__).resolve().parent.parent / "SOUL.md"


def soul_sha256() -> str | None:
    """Return the SHA256 of SOUL.md, or None if missing."""
    if not SOUL_PATH.is_file():
        return None
    h = hashlib.sha256()
    h.update(SOUL_PATH.read_bytes())
    return h.hexdigest()
