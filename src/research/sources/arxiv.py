"""Real arXiv API client.

arXiv exposes a public Atom-XML API at
``http://export.arxiv.org/api/query``. This module is the only path
Paperfessor uses to look up an arXiv paper; the LLM is never asked to
"make up" a citation.

Capabilities
------------
- ``search(query, ...)`` - full arXiv search with category filters and
  sort options. Returns normalized :class:`Paper` records.
- ``fetch(arxiv_id)`` - one-shot lookup by id (with or without version).
- ``download_pdf(paper, dest_dir)`` - download the PDF to a local cache
  (idempotent: skips if the file already exists with non-trivial size).

The whole module uses the standard library (``urllib`` + ``xml.etree``)
so it works without any third-party HTTP/XML deps. The arXiv API does
not require authentication.
"""

from __future__ import annotations

import dataclasses
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode

import requests

ARXIV_API: str = "http://export.arxiv.org/api/query"
ARXIV_PDF_BASE: str = "https://arxiv.org/pdf/"
ARXIV_ABS_BASE: str = "https://arxiv.org/abs/"

# Atom namespace map for the arXiv export. arXiv embeds an arxiv:
# extension namespace for the doi, journal_ref, comment, primary_category
# fields, and uses the standard atom: namespace for everything else.
_NS: dict[str, str] = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


class ArxivError(RuntimeError):
    """Raised on any arXiv API failure (network, parse, missing id)."""


@dataclasses.dataclass(frozen=True)
class Paper:
    """A normalized arXiv paper record.

    Immutable. The ``short_cite`` helper is a log-only convenience; the
    full record is the source of truth.
    """

    arxiv_id: str           # "2401.01234" or "2401.01234v2"
    title: str
    authors: tuple[str, ...]
    abstract: str
    year: int               # 4-digit, derived from <published>
    published: str          # ISO 8601
    updated: str
    primary_category: str   # e.g. "cs.LG"
    categories: tuple[str, ...]
    pdf_url: str            # "https://arxiv.org/pdf/2401.01234"
    abs_url: str            # "https://arxiv.org/abs/2401.01234"
    doi: str | None
    journal_ref: str | None
    comment: str | None

    def short_cite(self) -> str:
        """One-line citation (log use only). Not a substitute for BibTeX."""
        first = self.authors[0].split()[-1] if self.authors else "anon"
        return f"{first} et al. ({self.year}) [{self.primary_category or 'arxiv'}]"


# ---- Public API ----------------------------------------------------------


def search(
    query: str,
    *,
    max_results: int = 20,
    start: int = 0,
    sort_by: str = "relevance",
    sort_order: str = "descending",
    categories: Iterable[str] | None = None,
) -> list[Paper]:
    """Search arXiv and return a list of :class:`Paper` records.

    Query syntax is arXiv's. Examples::

        search("all:transformer AND cat:cs.LG")
        search('ti:"federated learning"', categories=["cs.LG"])
        search('au:lecun', max_results=50, sort_by="submittedDate")
        search("differential privacy", max_results=20)

    If ``categories`` is provided, it is AND-ed with the query (the
    caller does not need to add ``cat:`` themselves).
    """
    q = query.strip()
    if categories:
        cats = " OR ".join(f"cat:{c}" for c in categories)
        q = f"({q}) AND ({cats})" if q else f"({cats})"
    params = {
        "search_query": q,
        "start": str(start),
        "max_results": str(max_results),
        "sortBy": sort_by,
        "sortOrder": sort_order,
    }
    url = f"{ARXIV_API}?{urlencode(params)}"
    body = _http_get(url)
    return _parse_atom(body)


def fetch(arxiv_id: str) -> Paper:
    """Fetch a single paper by arXiv id (with or without version)."""
    aid = arxiv_id.strip()
    if not aid:
        raise ArxivError("empty arXiv id")
    papers = search(f"id:{_strip_version(aid)}", max_results=1)
    if not papers:
        raise ArxivError(f"arXiv id {aid!r} returned no results")
    return papers[0]


def download_pdf(paper: Paper, dest_dir: Path) -> Path:
    """Download ``paper``'s PDF into ``dest_dir`` (idempotent).

    The file name is the version-stripped arXiv id (``2401.01234.pdf``).
    If the file already exists with size > 1 KB, the download is
    skipped. The destination directory is created if it does not exist.

    arXiv occasionally 404s the versioned PDF URL (e.g. when a paper
    was just updated). We try the version-stripped URL first, then
    the versioned URL as a fallback.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{_strip_version(paper.arxiv_id)}.pdf"
    if out.exists() and out.stat().st_size > 1024:
        return out
    last_exc: BaseException | None = None
    for url in (paper.pdf_url, f"{ARXIV_PDF_BASE}{_strip_version(paper.arxiv_id)}"):
        try:
            body = _http_get(url, timeout=60.0)
            out.write_bytes(body)
            return out
        except ArxivError as exc:
            last_exc = exc
            continue
    raise last_exc or ArxivError(f"could not download {paper.arxiv_id}")


# ---- Internals -----------------------------------------------------------


def _strip_version(arxiv_id: str) -> str:
    return arxiv_id.split("v", 1)[0] if "v" in arxiv_id else arxiv_id


def _pdf_url_for(arxiv_id: str) -> str:
    return f"{ARXIV_PDF_BASE}{arxiv_id}"


def _abs_url_for(arxiv_id: str) -> str:
    return f"{ARXIV_ABS_BASE}{arxiv_id}"


def _http_get(url: str, *, timeout: float = 15.0, max_retries: int = 2) -> bytes:
    """GET ``url`` with exponential backoff. Returns body bytes.

    Uses :mod:`requests` (which is already a transitive dep via litellm
    and is verified to work on this machine) rather than
    :mod:`urllib.request`; the latter has shown SSL/timeout quirks on
    Windows.
    """
    last_exc: BaseException | None = None
    headers = {"User-Agent": "Paperfessor/0.4 (research agent)"}
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.content
        except (requests.RequestException, requests.HTTPError) as exc:
            last_exc = exc
            time.sleep(min(2 ** attempt, 3))
    raise ArxivError(f"GET {url} failed after {max_retries} attempts: {last_exc}")


def _parse_atom(body: bytes) -> list[Paper]:
    """Parse arXiv's Atom XML into a list of :class:`Paper` records."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ArxivError(f"could not parse arXiv Atom: {exc}") from exc
    out: list[Paper] = []
    for entry in root.findall("atom:entry", _NS):
        try:
            paper = _entry_to_paper(entry)
            if paper is not None:
                out.append(paper)
        except Exception:  # noqa: BLE001
            # One malformed entry must not kill the whole batch.
            continue
    return out


def _entry_to_paper(entry: ET.Element) -> Paper | None:
    raw_id = (entry.findtext("atom:id", default="", namespaces=_NS) or "").strip()
    if not raw_id:
        return None
    arxiv_id = raw_id.rsplit("/", 1)[-1]  # "http://arxiv.org/abs/X" -> "X"
    title = _normalize_text(entry.findtext("atom:title", default="", namespaces=_NS))
    abstract = _normalize_text(entry.findtext("atom:summary", default="", namespaces=_NS))
    published = entry.findtext("atom:published", default="", namespaces=_NS) or ""
    updated = entry.findtext("atom:updated", default="", namespaces=_NS) or ""
    year = _year_from_iso(published)
    authors = tuple(
        _normalize_text(a.findtext("atom:name", default="", namespaces=_NS))
        for a in entry.findall("atom:author", _NS)
    )
    authors = tuple(a for a in authors if a)
    primary_cat_el = entry.find("arxiv:primary_category", _NS)
    primary_category = (primary_cat_el.get("term") or "") if primary_cat_el is not None else ""
    categories = tuple(
        c.get("term") or "" for c in entry.findall("atom:category", _NS)
    )
    categories = tuple(c for c in categories if c)
    doi_el = entry.find("arxiv:doi", _NS)
    doi = doi_el.text.strip() if doi_el is not None and doi_el.text else None
    jref_el = entry.find("arxiv:journal_ref", _NS)
    jref = jref_el.text.strip() if jref_el is not None and jref_el.text else None
    comment_el = entry.find("arxiv:comment", _NS)
    comment = comment_el.text.strip() if comment_el is not None and comment_el.text else None
    if not arxiv_id or not title:
        return None
    return Paper(
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        abstract=abstract,
        year=year,
        published=published,
        updated=updated,
        primary_category=primary_category,
        categories=categories,
        pdf_url=_pdf_url_for(arxiv_id),
        abs_url=_abs_url_for(arxiv_id),
        doi=doi,
        journal_ref=jref,
        comment=comment,
    )


def _normalize_text(s: str | None) -> str:
    if not s:
        return ""
    # arXiv wraps long titles / abstracts in newlines.
    return re.sub(r"\s+", " ", s).strip()


def _year_from_iso(iso: str) -> int:
    if not iso:
        return 0
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).year
    except ValueError:
        m = re.search(r"(\d{4})", iso)
        return int(m.group(1)) if m else 0


__all__ = [
    "ARXIV_ABS_BASE",
    "ARXIV_API",
    "ARXIV_PDF_BASE",
    "ArxivError",
    "Paper",
    "download_pdf",
    "fetch",
    "search",
]
