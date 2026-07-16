"""OpenAlex API client.

OpenAlex is a fully open catalog of scholarly works (200M+ papers,
all metadata) with a free, no-auth REST API at
``https://api.openalex.org/``. It is the most generous of the three
sources Paperfessor uses: no per-IP rate limit at our scale, no
authentication, full abstracts (reconstructed from the inverted index
the API returns), DOIs, arXiv ids, venue names, and a ``best_oa_location``
that often points at the official venue PDF.

Because OpenAlex returns abstracts as an *inverted index* (a dict
mapping each word to its positions in the original text), we have to
reconstruct the abstract ourselves. See :func:`_reconstruct_abstract`.

Each :class:`OAPaper` is normalized to the same shape as
:class:`src.research.sources.s2.S2Paper` so the MS agent can treat
them interchangeably (it will see one ``Paper`` record regardless of
which source produced it).
"""

from __future__ import annotations

import dataclasses
import os
import re
import time
from typing import Iterable
from urllib.parse import quote

import requests

OA_BASE: str = "https://api.openalex.org"
# Plain UA — a mailto is only attached when the user configures a
# real contact address (PAPERFESSOR_CONTACT_EMAIL).
USER_AGENT: str = "Paperfessor/1.0 (research)"
_MAX_PER_PAGE: int = 50  # OpenAlex's hard cap


class OAError(RuntimeError):
    """Raised on any OpenAlex API failure."""


@dataclasses.dataclass(frozen=True)
class OAPaper:
    """A normalized OpenAlex work record."""

    oa_id: str                  # "W2741809807" (the OpenAlex id)
    doi: str | None             # "10.1162/neco.2006..." (no URL prefix)
    arxiv_id: str | None        # version-stripped, e.g. "2401.01234"
    title: str
    authors: tuple[str, ...]
    year: int
    publication_date: str | None
    venue: str                  # short venue name (e.g. "NeurIPS")
    venue_type: str             # "conference" | "journal" | "repository" | ...
    abstract: str
    is_oa: bool
    pdf_url: str | None
    landing_page_url: str | None
    cited_by_count: int
    referenced_works_count: int
    type: str                   # "article" | "preprint" | "book-chapter" | ...

    def short_cite(self) -> str:
        first = self.authors[0].split()[-1] if self.authors else "anon"
        venue = self.venue or "OA"
        return f"{first} et al. ({self.year}) [{venue}]"


# ---- Public API ----------------------------------------------------------


def search(
    query: str,
    *,
    limit: int = 20,
    page: int = 1,
    year_min: int | None = None,
    year_max: int | None = None,
    oa_only: bool = False,
    type_filter: str | None = None,
    sort: str | None = "publication_year:desc",
) -> list[OAPaper]:
    """Search OpenAlex by free text.

    Args:
        query: free text. OpenAlex matches against title + abstract.
        limit: max results (capped at 50 per call; the caller paginates).
        page: 1-indexed page number.
        year_min / year_max: inclusive publication-year range.
        oa_only: if True, keep only open-access works.
        type_filter: e.g. ``"article"`` to drop preprints/book chapters.
        sort: OpenAlex sort spec, e.g. ``"cited_by_count:desc"``.
    """
    q = query.strip()
    if not q:
        return []
    filters: list[str] = []
    if year_min is not None or year_max is not None:
        ymin = year_min if year_min is not None else 0
        ymax = year_max if year_max is not None else 9999
        filters.append(f"publication_year:{ymin}-{ymax}")
    if oa_only:
        filters.append("is_oa:true")
    if type_filter:
        filters.append(f"type:{type_filter}")
    per_page = min(limit, _MAX_PER_PAGE)
    params: list[tuple[str, str]] = [
        ("search", q),
        ("per_page", str(per_page)),
        ("page", str(page)),
    ]
    # OpenAlex "polite pool": a REAL contact email gets a larger rate
    # budget. Only sent when the user configures one — sending a fake
    # address would violate OpenAlex's politeness policy.
    contact = os.environ.get("PAPERFESSOR_CONTACT_EMAIL", "").strip()
    if contact and "@" in contact:
        params.append(("mailto", contact))
    if filters:
        params.append(("filter", ",".join(filters)))
    if sort:
        params.append(("sort", sort))
    qs = "&".join(f"{k}={quote(str(v), safe=':,')}" for k, v in params)
    body = _http_get(f"{OA_BASE}/works?{qs}")
    return [_row_to_paper(row) for row in (body.get("results") or [])]


def fetch_by_arxiv_id(arxiv_id: str) -> OAPaper:
    """Look up a paper by (version-stripped) arXiv id.

    OpenAlex indexes arXiv preprints but the lookup is not reliable
    (the ``doi:10.48550/arxiv.X`` form returns 404 in 2026). This
    method falls back to a free-text search on the arXiv id and picks
    the highest-cited match. For most uses, prefer
    :func:`src.research.sources.arxiv.fetch` (the arXiv API), which
    is authoritative; use this only to enrich an arXiv record with
    OpenAlex metadata (venue, citation count, etc.).
    """
    aid = arxiv_id.strip().split("v", 1)[0]
    if not aid:
        raise OAError("empty arXiv id")
    candidates = search(aid, limit=5, type_filter=None)
    if not candidates:
        raise OAError(f"OpenAlex: arXiv {aid!r} not found")
    candidates.sort(key=lambda p: p.cited_by_count, reverse=True)
    return candidates[0]


def fetch_by_doi(doi: str) -> OAPaper:
    """Look up a paper by DOI. ``doi`` may or may not include the ``doi:`` prefix."""
    d = doi.strip()
    if d.lower().startswith("doi:"):
        d = d[4:]
    body = _http_get(f"{OA_BASE}/works/{quote(d, safe='/')}")
    return _row_to_paper(body)


# ---- Internals -----------------------------------------------------------


def _row_to_paper(row: dict) -> OAPaper:
    oa_id = _id_from_url(row.get("id"))
    doi = (row.get("doi") or "").lower()
    if doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]
    doi = doi or None
    ids = row.get("ids") or {}
    arxiv_id = ids.get("openalex")  # not used; we extract from ids/doi
    # OpenAlex exposes arXiv ids via the "doi" of the arXiv wrapper record,
    # or via ids["arxiv"]. Prefer ids["arxiv"] when present.
    arxiv_id = ids.get("arxiv") or None
    if not arxiv_id and doi and doi.startswith("10.48550/arxiv."):
        arxiv_id = doi[len("10.48550/arxiv."):].strip()
    title = _norm(row.get("title") or row.get("display_name"))
    abstract = _reconstruct_abstract(row.get("abstract_inverted_index") or {})
    authors = tuple(
        _author_name(a) for a in (row.get("authorships") or []) if a
    )
    authors = tuple(a for a in authors if a)
    year = int(row.get("publication_year") or 0)
    pub_date = row.get("publication_date") or None
    primary = row.get("primary_location") or {}
    source = primary.get("source") or {}
    venue = _norm(source.get("display_name"))
    venue_type = _norm(source.get("type"))
    is_oa = bool(row.get("open_access", {}).get("is_oa"))
    pdf_url = primary.get("pdf_url") or None
    landing = primary.get("landing_page_url") or None
    cited_by = int(row.get("cited_by_count") or 0)
    # referenced_works is a list of ids; its length is the count.
    refs = row.get("referenced_works") or []
    typ = _norm(row.get("type")) or "unknown"
    return OAPaper(
        oa_id=oa_id,
        doi=doi,
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        year=year,
        publication_date=pub_date,
        venue=venue,
        venue_type=venue_type,
        abstract=abstract,
        is_oa=is_oa,
        pdf_url=pdf_url,
        landing_page_url=landing,
        cited_by_count=cited_by,
        referenced_works_count=len(refs),
        type=typ,
    )


def _id_from_url(url: str | None) -> str:
    """OpenAlex returns ids as full URLs (e.g. ``https://openalex.org/W123``).
    We keep just the trailing token.
    """
    if not url:
        return ""
    return url.rsplit("/", 1)[-1].strip()


def _author_name(a: dict) -> str:
    au = a.get("author") or {}
    return _norm(au.get("display_name"))


def _norm(s) -> str:
    if s is None:
        return ""
    return str(s).strip()


def _reconstruct_abstract(inv: dict) -> str:
    """Reconstruct the abstract from OpenAlex's inverted index.

    The API returns ``{"word": [pos1, pos2, ...]}``. We lay the words
    out at their positions. Missing positions are left as gaps. The
    output is the original abstract text (with light whitespace fixes).
    """
    if not inv:
        return ""
    max_pos = 0
    for positions in inv.values():
        if positions:
            max_pos = max(max_pos, max(positions))
    slots: list[str] = [""] * (max_pos + 1)
    for word, positions in inv.items():
        for p in positions:
            if 0 <= p < len(slots):
                slots[p] = word
    text = " ".join(slots)
    # OpenAlex stores the original abstract with light-tokenized words;
    # fix the most common cases: "transformer - based" -> "transformer-based",
    # and the leading/trailing punctuation that often shows up.
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _http_get(url: str, *, max_retries: int = 4) -> dict:
    """GET ``url`` and return parsed JSON. Retries on 429 / 5xx.

    OpenAlex is more permissive than S2, but we still retry on rate
    limits. The shared ``mailto``-tagged User-Agent is required by the
    OpenAlex ``polite pool`` policy; without it, rate limits are tighter.
    """
    headers = {"User-Agent": USER_AGENT}
    last_exc: BaseException | None = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                time.sleep(min(2 ** attempt, 10))
                last_exc = OAError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(min(2 ** attempt, 10))
    raise OAError(f"OpenAlex GET {url} failed: {last_exc}")


__all__ = [
    "OA_BASE",
    "OAError",
    "OAPaper",
    "fetch_by_arxiv_id",
    "fetch_by_doi",
    "search",
]
