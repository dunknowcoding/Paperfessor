"""PDF text extraction.

Wraps :mod:`pypdf` so the rest of Paperfessor only sees a clean
string-in / string-out API. The MS agent uses this after
:func:`src.research.sources.arxiv.download_pdf` to feed the LLM the
actual paper body, not just the abstract.

The output is plain text, one page per blank-line-separated paragraph.
A small section header (``PAGE n / m``) is prepended to each page so
downstream prompts can reference the page number when they cite the
paper.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PdfError(RuntimeError):
    """Raised when a PDF cannot be loaded or extracted."""


def load_text(pdf_path: Path, *, max_pages: int | None = None) -> str:
    """Extract text from a PDF file.

    Args:
        pdf_path: path to the .pdf file. Must exist.
        max_pages: stop after this many pages (``None`` = all).

    Returns:
        Concatenated text, one page per blank-line-separated paragraph.
        Each page is prefixed with ``[PAGE n/m]`` so the LLM can cite
        the page number in its output.

    Raises:
        PdfError: on missing file, missing dep, or read failure.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise PdfError("pypdf is not installed; run `pip install pypdf`") from exc
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise PdfError(f"PDF not found: {pdf_path}")
    try:
        reader = PdfReader(str(pdf_path))
    except Exception as exc:  # noqa: BLE001
        raise PdfError(f"could not open PDF {pdf_path}: {exc}") from exc
    n = len(reader.pages)
    limit = min(n, max_pages) if max_pages else n
    chunks: list[str] = []
    for i in range(limit):
        try:
            page_text = reader.pages[i].extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("page %d of %s failed: %s", i + 1, pdf_path, exc)
            page_text = ""
        page_text = page_text.strip()
        if not page_text:
            continue
        chunks.append(f"[PAGE {i + 1}/{limit}]\n{page_text}")
    return "\n\n".join(chunks)


def page_count(pdf_path: Path) -> int:
    """Return the number of pages in ``pdf_path``."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise PdfError("pypdf is not installed") from exc
    return len(PdfReader(str(pdf_path)).pages)


__all__ = ["PdfError", "load_text", "page_count"]
