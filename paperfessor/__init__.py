"""Paperfessor.

A research direction, a top-innovation paper draft, and a runnable
code project — across one unified, multilingual GUI + CLI.
"""

from __future__ import annotations

import sys

# Keep runtime bytecode caches out of the repository tree. The project
# already treats the workspace as the only disposable runtime area.
sys.dont_write_bytecode = True

from paperfessor._meta import __author__, __license__, __version__

__all__ = ["__author__", "__license__", "__version__"]
