"""``python -m paperfessor`` entry point."""

from __future__ import annotations

import sys

from paperfessor.cli.app import app

if __name__ == "__main__":
    sys.exit(app())
