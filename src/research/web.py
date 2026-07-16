"""Playwright-based web tools.

Why this module exists
-----------------------
The :mod:`src.research.sources` API clients cover the easy cases
(arXiv, OpenAlex, Semantic Scholar). For everything else -- Google
Scholar (no free API), paywalled publisher pages, papers hosted on
lab sites, arXiv papers that return a ``js-rendered`` abstract, etc.
-- we need a real browser. This module is that browser.

The module is intentionally small and has no external deps beyond
:mod:`playwright` itself. It does *not* call the LLM: the LLM is the
*consumer* of the structured records the web search produces, not
the producer.

Components
----------
- :class:`BrowserPool` - a single Chromium instance shared across
  calls (one browser launch per process, multiple contexts/pages).
- :func:`search_google_scholar` - hit Google Scholar, return a list
  of normalized :class:`ScholarResult` records (title, authors,
  venue, year, cited-by, link).
- :func:`fetch_url` - GET any URL and return the rendered HTML.
- :func:`screenshot_url` - render a URL to a PNG (full page or
  viewport).
- :func:`screenshot_pdf_page` - render a specific page of a PDF to
  a PNG (uses Chromium's built-in PDF viewer; works on file:// URLs).
- :func:`screenshot_paper_figures` - given a paper PDF and a list of
  page ranges, emit one PNG per range. Used by the MS agent to hand
  figures to the LLM for visual analysis.
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import re
import threading
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus, unquote

logger = logging.getLogger(__name__)


# ---- Public record types ------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ScholarResult:
    """A normalized Google Scholar result row."""

    title: str
    authors: str               # raw "A. Smith, B. Jones, ..." (Scholar formatting)
    venue: str                 # "NeurIPS 2023" or "arXiv preprint"
    year: int
    cited_by: int
    detail_url: str            # the per-paper Scholar cluster URL
    pdf_url: str | None        # the [PDF] link if Scholar shows one
    snippet: str               # the snippet under the title


# ---- Browser lifecycle --------------------------------------------------


_BROWSER_LOCK = threading.Lock()
_BROWSER: object | None = None  # playwright.sync_api.Browser, lazy


def _launch_browser():
    """Launch (or reuse) a single Chromium browser.

    We prefer the system Chrome (``channel="chrome"``) so we do not
    have to download a 170 MB Playwright-bundled Chromium. The
    fallback ``chromium`` is the bundled binary; install it via
    ``playwright install chromium`` if the system Chrome is missing.
    """
    from playwright.sync_api import sync_playwright

    with _BROWSER_LOCK:
        global _BROWSER
        if _BROWSER is not None:
            return _BROWSER
        pw = sync_playwright().start()
        for attempt in (1, 2):
            try:
                if attempt == 1:
                    _BROWSER = pw.chromium.launch(
                        headless=True, channel="chrome",
                        args=["--no-sandbox", "--disable-dev-shm-usage"],
                    )
                else:
                    _BROWSER = pw.chromium.launch(
                        headless=True,
                        args=["--no-sandbox", "--disable-dev-shm-usage"],
                    )
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("browser launch attempt %d failed: %s", attempt, exc)
                if attempt == 2:
                    raise
        return _BROWSER


def close_browser() -> None:
    """Tear down the shared browser. Idempotent."""
    global _BROWSER
    with _BROWSER_LOCK:
        if _BROWSER is not None:
            try:
                _BROWSER.close()
            except Exception:  # noqa: BLE001
                pass
            _BROWSER = None


@contextlib.contextmanager
def _new_page():
    """Yield a fresh page from the shared browser, closing it on exit."""
    browser = _launch_browser()
    ctx = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1366, "height": 900},
    )
    page = ctx.new_page()
    try:
        yield page
    finally:
        try:
            ctx.close()
        except Exception:  # noqa: BLE001
            pass


# ---- Google Scholar ------------------------------------------------------


_GSCHOLAR_HOST = "https://scholar.google.com"


def search_google_scholar(
    query: str,
    *,
    limit: int = 10,
    year_min: int | None = None,
    year_max: int | None = None,
) -> list[ScholarResult]:
    """Search Google Scholar and return up to ``limit`` parsed results.

    Google Scholar does not expose a public API; we render the search
    page and parse the result rows. The site has aggressive bot
    detection; we set a real browser User-Agent and load the page
    with a normal navigation (no direct API requests). If Scholar
    returns a CAPTCHA page, this method returns ``[]`` and logs a
    warning -- callers should fall back to arXiv / OpenAlex.
    """
    q = quote_plus(query)
    url = f"{_GSCHOLAR_HOST}/scholar?q={q}&hl=en&as_sdt=0%2C5"
    if year_min or year_max:
        lo = year_min or ""
        hi = year_max or ""
        url += f"&as_ylo={lo}&as_yhi={hi}"
    out: list[ScholarResult] = []
    try:
        with _new_page() as page:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Give JS a moment to settle (Scholar renders results in JS).
            page.wait_for_timeout(1500)
            # If we got a CAPTCHA, bail.
            if "captcha" in (page.content() or "").lower()[:4000]:
                logger.warning("Google Scholar returned a CAPTCHA; skipping")
                return []
            results = page.locator("div.gs_r.gs_or.gs_scl").all()[:limit]
            if not results:
                # Older markup fallback.
                results = page.locator("div.gs_r").all()[:limit]
            for r in results:
                parsed = _parse_scholar_row(r)
                if parsed is not None:
                    out.append(parsed)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scholar search failed for %r: %s", query, exc)
    return out


def _parse_scholar_row(locator) -> ScholarResult | None:
    """Parse one Scholar result row."""
    try:
        title_el = locator.locator("h3.gs_rt").first
        title = title_el.inner_text().strip() if title_el.count() else ""
        if title.startswith("[PDF]") or title.startswith("[HTML]") or title.startswith("[BOOK]"):
            title = title.split("]", 1)[1].strip()
        # The cluster (per-paper) URL lives in the title <a>.
        href = ""
        a = title_el.locator("a").first
        if a.count():
            href = a.get_attribute("href") or ""
        # Authors / venue / year live in div.gs_a.
        gs_a = locator.locator("div.gs_a").first
        meta = gs_a.inner_text() if gs_a.count() else ""
        year, venue = _split_meta(meta)
        # Cited-by lives in div.gs_fl > a containing "Cited by".
        cited = 0
        cited_link = locator.locator("a:has-text('Cited by')").first
        if cited_link.count():
            m = re.search(r"Cited by\s+(\d+)", cited_link.inner_text())
            if m:
                cited = int(m.group(1))
        # Snippet.
        snip_el = locator.locator("div.gs_rs").first
        snippet = snip_el.inner_text().strip() if snip_el.count() else ""
        # [PDF] link is in gs_or_ggsm / gs_or_pdf class blocks.
        pdf_url = None
        pdf_a = locator.locator("div.gs_or_ggsm a, a.gs_or_pdf").first
        if pdf_a.count():
            pdf_url = pdf_a.get_attribute("href") or None
        if not title:
            return None
        return ScholarResult(
            title=title, authors=meta.split("-", 1)[0].strip() if meta else "",
            venue=venue, year=year, cited_by=cited,
            detail_url=href or "", pdf_url=pdf_url, snippet=snippet,
        )
    except Exception:  # noqa: BLE001
        return None


def _split_meta(meta: str) -> tuple[int, str]:
    """Pull year + venue from a Scholar ``div.gs_a`` string.

    Example meta: ``A Smith, B Jones - NeurIPS 2023 - proceedings.neurips.cc``
    We want ``(2023, 'NeurIPS')``.
    """
    if not meta:
        return 0, ""
    year = 0
    ymatch = re.search(r"\b(19|20)\d{2}\b", meta)
    if ymatch:
        year = int(ymatch.group(0))
    # Take the token right before the year as the venue.
    venue = ""
    if ymatch:
        before = meta[: ymatch.start()].rstrip(" -")
        # The last ``-`` separated chunk is usually the venue.
        if "-" in before:
            venue = before.rsplit("-", 1)[-1].strip()
        else:
            venue = before
    return year, venue


# ---- Generic URL fetch + screenshot -------------------------------------


def fetch_url(url: str, *, timeout_ms: int = 30000) -> str:
    """GET ``url`` in a real browser, return the rendered HTML."""
    with _new_page() as page:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(800)  # let JS settle
        return page.content()


def screenshot_url(
    url: str, out_path: Path, *,
    full_page: bool = True, timeout_ms: int = 30000,
) -> Path:
    """Render ``url`` and save a PNG screenshot to ``out_path``."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with _new_page() as page:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(800)
        page.screenshot(path=str(out_path), full_page=full_page)
    return out_path


def screenshot_pdf_page(
    pdf_path: Path, page_num: int, out_path: Path, *,
    scale: float = 2.0,
) -> Path:
    """Render one page of a local PDF to a PNG.

    Uses :mod:`pypdfium2` (a self-contained PDF rasterizer) rather
    than Chromium's PDF viewer, because the latter does not render
    ``file://`` PDFs in headless mode.
    """
    pdf_path = Path(pdf_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RuntimeError(
            "pypdfium2 is not installed; run `pip install pypdfium2`"
        ) from exc
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    pdf = pdfium.PdfDocument(str(pdf_path))
    if not (0 <= page_num < len(pdf)):
        raise IndexError(f"page {page_num} out of range (PDF has {len(pdf)} pages)")
    image = pdf[page_num].render(scale=scale).to_pil()
    image.save(str(out_path))
    return out_path


def screenshot_paper_figures(
    pdf_path: Path, page_ranges: Iterable[tuple[int, int]], out_dir: Path,
    *,
    scale: float = 2.0,
) -> list[Path]:
    """Render each (start, end) page range as one PNG per page.

    Used by the MS agent to capture "figure regions" of a paper: the
    caller picks page numbers where the paper says ``Figure 1`` etc.
    and the module emits one PNG per page in the range.
    """
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for start, end in page_ranges:
        for p in range(start, end + 1):
            out.append(screenshot_pdf_page(
                pdf_path, p, out_dir / f"page_{p:04d}.png", scale=scale,
            ))
    return out


# ---- Online paper reading -----------------------------------------------


def fetch_paper_online(
    url: str, out_path: Path | None = None, *,
    render_to_pdf: bool = False, timeout_ms: int = 30000,
) -> str:
    """Open a paper URL in the browser and return the rendered HTML.

    If ``out_path`` is given, the rendered HTML is saved there. If
    ``render_to_pdf`` is True, the page is also printed to a PDF
    next to the HTML (Chromium's ``page.pdf()``).
    """
    out_path = Path(out_path) if out_path else None
    with _new_page() as page:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(800)
        html = page.content()
        if out_path is not None:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(html, encoding="utf-8")
        if render_to_pdf and out_path is not None:
            page.pdf(path=str(out_path.with_suffix(".pdf")))
    return html


__all__ = [
    "ScholarResult",
    "close_browser",
    "fetch_paper_online",
    "fetch_url",
    "screenshot_paper_figures",
    "screenshot_pdf_page",
    "screenshot_url",
    "search_google_scholar",
]
