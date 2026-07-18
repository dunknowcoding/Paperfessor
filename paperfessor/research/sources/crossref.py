"""Crossref API client — broad, cross-disciplinary paper discovery.

Crossref (https://api.crossref.org) indexes 150M+ scholarly works
across EVERY discipline (medicine, economics, social science, law,
humanities, engineering), not just CS/physics like arXiv. It is free,
needs no authentication, and honors a "polite pool" when a contact
email is provided (PAPERFESSOR_CONTACT_EMAIL) for better rate limits.

Records are normalized to the same shape the MS agent consumes from
OpenAlex / arXiv, so the three sources are interchangeable. Crossref
rarely carries abstracts, so ``abstract`` may be empty — OpenAlex is
the abstract-rich source; Crossref broadens DISCOVERY across fields.
"""

from __future__ import annotations

import dataclasses
import os
import re
from urllib.parse import quote

import requests

CR_BASE = "https://api.crossref.org/works"
USER_AGENT = "Paperfessor/1.0 (research; cross-disciplinary search)"


class CrossrefError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class CRPaper:
    doi: str | None
    title: str
    authors: tuple[str, ...]
    year: int
    venue: str
    venue_type: str
    abstract: str
    landing_page_url: str | None
    cited_by_count: int


def _strip_jats(text: str) -> str:
    """Crossref abstracts, when present, are JATS XML — strip tags."""
    return re.sub(r"<[^>]+>", "", text or "").strip()


def search(query: str, *, limit: int = 12, year_min: int | None = None,
           timeout: float = 20.0) -> list[CRPaper]:
    """Search Crossref for ``query`` (any discipline)."""
    q = (query or "").strip()
    if not q:
        return []
    params: list[tuple[str, str]] = [
        ("query.bibliographic", q),
        ("rows", str(max(1, min(limit, 50)))),
        ("select", "DOI,title,author,issued,container-title,type,"
                   "abstract,URL,is-referenced-by-count"),
        ("sort", "relevance"),
    ]
    if year_min:
        params.append(("filter", f"from-pub-date:{year_min}-01-01"))
    contact = os.environ.get("PAPERFESSOR_CONTACT_EMAIL", "").strip()
    if contact and "@" in contact:
        params.append(("mailto", contact))
    qs = "&".join(f"{k}={quote(str(v), safe=':,-.')}" for k, v in params)
    try:
        resp = requests.get(f"{CR_BASE}?{qs}",
                            headers={"User-Agent": USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
        items = resp.json().get("message", {}).get("items", [])
    except Exception as exc:  # noqa: BLE001
        raise CrossrefError(str(exc)) from exc
    out: list[CRPaper] = []
    for it in items:
        title = " ".join(it.get("title", []) or []).strip()
        if not title:
            continue
        authors: list[str] = []
        for a in it.get("author", []) or []:
            name = " ".join(x for x in (a.get("given"), a.get("family")) if x)
            if name:
                authors.append(name)
        year = 0
        parts = (it.get("issued", {}) or {}).get("date-parts", [[None]])
        if parts and parts[0] and parts[0][0]:
            year = int(parts[0][0])
        out.append(CRPaper(
            doi=it.get("DOI"),
            title=title,
            authors=tuple(authors),
            year=year,
            venue=" ".join(it.get("container-title", []) or [])[:120],
            venue_type=str(it.get("type", "")),
            abstract=_strip_jats(it.get("abstract", "")),
            landing_page_url=it.get("URL"),
            cited_by_count=int(it.get("is-referenced-by-count", 0) or 0),
        ))
    return out


__all__ = ["CRPaper", "CrossrefError", "search"]
