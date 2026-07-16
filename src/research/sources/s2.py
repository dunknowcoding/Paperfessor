"""Semantic Scholar Graph API client.

Semantic Scholar indexes papers from arXiv AND the major conferences
(NeurIPS, ICML, ICLR, ACL, EMNLP, CVPR, KDD, AAAI, ...) and exposes a
free, unauthenticated REST API at
``https://api.semanticscholar.org/graph/v1/``.

This module is the cross-venue lookup path. For each paper it returns
the title, authors, year, **published venue** (the missing piece arXiv
does not provide), citation count, and an openAccessPdf URL when one
exists. It also resolves an arXiv id (or DOI) to the S2 paper id, which
unlocks the citation graph (``get_references`` / ``get_citations``).

Rate limits: S2 allows ~100 req/s per IP for unauthenticated traffic
in bursts; in practice the shared cluster is fine for the volumes a
single research project needs. The client does an exponential-backoff
retry on 429 / 5xx so a single paper lookup never crashes the MS agent.
"""

from __future__ import annotations

import dataclasses
import threading
import time
from typing import Iterable
from urllib.parse import quote

import requests

S2_BASE: str = "https://api.semanticscholar.org/graph/v1"

# Default field bundle for paper lookups. S2 lets you ask for only the
# fields you want; we pick a broad set so callers can render a survey
# row from a single response.
_FIELDS_PAPER: str = (
    "paperId,externalIds,title,abstract,year,venue,publicationVenue,"
    "authors,citationCount,referenceCount,influentialCitationCount,"
    "isOpenAccess,openAccessPdf,fieldsOfStudy,publicationDate,journal"
)

# Tighter field bundle for batch citation-graph calls (references /
# citations) where each entry is small.
_FIELDS_TINY: str = "paperId,externalIds,title,year,venue,authors"


class S2Error(RuntimeError):
    """Raised on any Semantic Scholar API failure."""


@dataclasses.dataclass(frozen=True)
class S2Paper:
    """A normalized Semantic Scholar paper record."""

    s2_id: str                       # "abc123..." (40-char sha)
    title: str
    authors: tuple[str, ...]
    year: int
    venue: str                       # short venue name, e.g. "NeurIPS"
    publication_date: str | None
    abstract: str
    doi: str | None
    arxiv_id: str | None             # version-stripped, e.g. "2401.01234"
    citation_count: int
    reference_count: int
    influential_citation_count: int
    is_open_access: bool
    open_access_pdf_url: str | None
    fields_of_study: tuple[str, ...]

    def short_cite(self) -> str:
        first = self.authors[0].split()[-1] if self.authors else "anon"
        venue = self.venue or "S2"
        return f"{first} et al. ({self.year}) [{venue}]"


# ---- Public API ----------------------------------------------------------


def search(
    query: str,
    *,
    limit: int = 20,
    offset: int = 0,
    year_min: int | None = None,
    year_max: int | None = None,
    fields_of_study: Iterable[str] | None = None,
) -> list[S2Paper]:
    """Search S2 by free-text query. Returns a list of S2Paper.

    Args:
        query: free text. S2 will match against title, abstract, authors.
        limit: max results (S2 caps at 100 per call).
        offset: pagination offset.
        year_min / year_max: filter by year range (inclusive).
        fields_of_study: e.g. ["Computer Science", "Linguistics"].
    """
    q = query.strip()
    if not q:
        return []
    params: list[tuple[str, str]] = [
        ("query", q),
        ("limit", str(min(limit, 100))),
        ("offset", str(offset)),
        ("fields", _FIELDS_PAPER),
    ]
    if year_min is not None:
        params.append(("year", f"{year_min}-{year_max if year_max else ''}"))
    elif year_max is not None:
        params.append(("year", f"-{year_max}"))
    if fields_of_study:
        for f in fields_of_study:
            params.append(("fieldsOfStudy", f))
    qs = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params)
    body = _http_get(f"{S2_BASE}/paper/search?{qs}")
    data = body.get("data") or []
    return [_row_to_paper(row) for row in data if row]


def fetch_by_arxiv_id(arxiv_id: str) -> S2Paper:
    """Look up a paper by its (version-stripped) arXiv id."""
    aid = arxiv_id.strip().split("v", 1)[0]
    if not aid:
        raise S2Error("empty arXiv id")
    body = _http_get(f"{S2_BASE}/paper/arXiv:{quote(aid, safe='')}?fields={_FIELDS_PAPER}")
    return _row_to_paper(body)


def fetch_by_doi(doi: str) -> S2Paper:
    """Look up a paper by DOI (e.g. ``10.1162/neco.2006.18.7.1345``)."""
    body = _http_get(f"{S2_BASE}/paper/DOI:{quote(doi.strip(), safe='')}?fields={_FIELDS_PAPER}")
    return _row_to_paper(body)


def get_references(s2_id: str, *, limit: int = 50) -> list[S2Paper]:
    """Return the papers this paper cites (outgoing references)."""
    return _get_edges(s2_id, "references", limit=limit)


def get_citations(s2_id: str, *, limit: int = 50) -> list[S2Paper]:
    """Return the papers that cite this paper (incoming citations)."""
    return _get_edges(s2_id, "citations", limit=limit)


# ---- Internals -----------------------------------------------------------

# Process-wide rate limiter. The S2 shared cluster is per-IP; to keep
# a single survey run polite we serialize requests and enforce a
# minimum gap between them. Override via env if you have an S2 key.
_MIN_GAP_S: float = 1.5
_gate = threading.Lock()
_last_ts: list[float] = [0.0]


def _throttle() -> None:
    """Sleep just enough to keep two S2 calls at least ``_MIN_GAP_S`` apart."""
    with _gate:
        now = time.monotonic()
        wait = _MIN_GAP_S - (now - _last_ts[0])
        if wait > 0:
            time.sleep(wait)
        _last_ts[0] = time.monotonic()


def _get_edges(s2_id: str, kind: str, *, limit: int) -> list[S2Paper]:
    """GET /paper/{id}/{references|citations} and parse the response."""
    body = _http_get(
        f"{S2_BASE}/paper/{quote(s2_id, safe='')}/{kind}"
        f"?fields={_FIELDS_TINY}&limit={min(limit, 100)}"
    )
    data = body.get("data") or []
    out: list[S2Paper] = []
    for row in data:
        # The "citingPaper" / "citedPaper" wrapper depends on the endpoint.
        inner = row.get("citingPaper") or row.get("citedPaper") or row
        if inner:
            out.append(_row_to_paper(inner))
    return out


def _row_to_paper(row: dict) -> S2Paper:
    """Normalize an S2 paper JSON row into an :class:`S2Paper`."""
    s2_id = str(row.get("paperId") or "")
    title = _norm(row.get("title"))
    abstract = _norm(row.get("abstract"))
    year = int(row.get("year") or 0)
    venue = _venue_name(row.get("publicationVenue") or row.get("venue"))
    pub_date = row.get("publicationDate") or None
    authors = tuple(
        _author_name(a) for a in (row.get("authors") or []) if a
    )
    authors = tuple(a for a in authors if a)
    external = row.get("externalIds") or {}
    doi = (external.get("DOI") or "").strip() or None
    arxiv_id = (external.get("ArXiv") or "").strip() or None
    is_oa = bool(row.get("isOpenAccess"))
    pdf_url = None
    oa = row.get("openAccessPdf") or {}
    if isinstance(oa, dict):
        url = oa.get("url")
        if url:
            pdf_url = str(url)
    fos = tuple(
        str(f) for f in (row.get("fieldsOfStudy") or []) if f
    )
    return S2Paper(
        s2_id=s2_id,
        title=title,
        authors=authors,
        year=year,
        venue=venue,
        publication_date=pub_date,
        abstract=abstract,
        doi=doi,
        arxiv_id=arxiv_id,
        citation_count=int(row.get("citationCount") or 0),
        reference_count=int(row.get("referenceCount") or 0),
        influential_citation_count=int(row.get("influentialCitationCount") or 0),
        is_open_access=is_oa,
        open_access_pdf_url=pdf_url,
        fields_of_study=fos,
    )


def _venue_name(v) -> str:
    """S2 returns venue either as a string or as a dict with 'name'."""
    if not v:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        return _norm(v.get("name"))
    return ""


def _author_name(a: dict) -> str:
    if not isinstance(a, dict):
        return ""
    return _norm(a.get("name"))


def _norm(s) -> str:
    if s is None:
        return ""
    return str(s).strip()


def _http_get(url: str, *, max_retries: int = 5) -> dict:
    """GET ``url`` and return parsed JSON. Retries on 429 / 5xx.

    The S2 shared cluster is rate-limited per-IP. A 429 may need a
    longer wait than the standard exponential backoff, so we use a
    floor of 5s on the first retry and respect S2's ``Retry-After``
    header when it is set. The :func:`_throttle` gate enforces a
    minimum gap between calls so a single survey run does not exceed
    the per-second budget.
    """
    _throttle()
    headers = {
        "User-Agent": "Paperfessor/0.4 (research; mailto:research@paperfessor.local)"
    }
    last_exc: BaseException | None = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else max(5, 2 ** attempt)
                time.sleep(min(wait, 30))
                last_exc = S2Error(f"HTTP {resp.status_code}: {resp.text[:200]}")
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(min(2 ** attempt, 8))
    raise S2Error(f"S2 GET {url} failed: {last_exc}")



def find_arxiv_id_for_doi(doi: str) -> str | None:
    """Look up the arXiv id for a given DOI via Semantic Scholar.

    Returns the canonical arXiv id (without version suffix) or
    None if no arXiv version is found. Uses the S2 paper lookup
    endpoint which exposes the ``externalIds`` field.
    """
    if not doi:
        return None
    doi = doi.strip()
    if not doi:
        return None
    url = f"{S2_BASE}/paper/DOI:{doi}"
    try:
        resp = requests.get(
            url,
            params={"fields": "externalIds"},
            headers={"User-Agent": "Paperfessor/0.4 (research)"},
            timeout=30,
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    ext = data.get("externalIds") or {}
    arxiv_id = ext.get("ArXiv")
    if not arxiv_id:
        return None
    # Strip version suffix (e.g. "2108.09896v2" -> "2108.09896").
    return str(arxiv_id).split("v", 1)[0]

__all__ = [
    "S2_BASE",
    "S2Error",
    "S2Paper",
    "fetch_by_arxiv_id",
    "fetch_by_doi",
    "get_citations",
    "get_references",
    "search",
]
