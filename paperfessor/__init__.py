"""Paperfessor.

A research direction, a top-innovation paper draft, and a runnable
code project — across one unified, multilingual GUI + CLI.
"""

from __future__ import annotations

import os
import sys

# Keep runtime bytecode caches out of the repository tree. The project
# already treats the workspace as the only disposable runtime area.
sys.dont_write_bytecode = True

# Guard against the OpenMP duplicate-runtime abort (OMP Error #15,
# libiomp5md.dll) that happens on Windows/conda when numpy, scipy,
# scikit-learn, matplotlib, and/or torch each bundle their own OpenMP.
# Set BEFORE any of those import. ``setdefault`` respects a user
# override. This is the documented, widely-used workaround.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from paperfessor._meta import __author__, __license__, __version__

__all__ = ["__author__", "__license__", "__version__"]
