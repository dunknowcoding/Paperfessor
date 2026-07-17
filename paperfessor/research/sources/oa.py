"""Open-access full-text resolvers beyond arXiv.

The survey's readable-paper rate decides paper quality, so the MS
climbs a ladder of REAL open-access sources before declaring a paper
inaccessible:

1. arXiv version of the DOI          (sources.s2.find_arxiv_id_for_doi)
2. Semantic Scholar openAccessPdf    (sources.s2.open_access_pdf_for_doi)
3. Unpaywall best OA location        (this module; needs a real email)
4. Playwright-rendered HTML          (research.web, caller's fallback)

Unpaywall (https://unpaywall.org/products/api) is a free index of
legal OA copies keyed by DOI. Its terms require a genuine contact
email; we therefore only call it when the user has configured
``PAPERFESSOR_CONTACT_EMAIL``.
"""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

UNPAYWALL_BASE = "https://api.unpaywall.org/v2"


def unpaywall_pdf_for_doi(doi: str, *, timeout: float = 20.0) -> str | None:
    """Return the best legal OA PDF URL Unpaywall knows for ``doi``.

    Returns None when no OA copy exists, on any error, or when no
    contact email is configured (Unpaywall's terms require one).
    """
    email = os.environ.get("PAPERFESSOR_CONTACT_EMAIL", "").strip()
    if not email or "@" not in email:
        return None
    doi = (doi or "").strip()
    if not doi:
        return None
    try:
        resp = requests.get(
            f"{UNPAYWALL_BASE}/{doi}",
            params={"email": email},
            headers={"User-Agent": "Paperfessor/1.0 (research)"},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
    except (requests.RequestException, ValueError):
        return None
    loc = data.get("best_oa_location") or {}
    url = loc.get("url_for_pdf") or loc.get("url")
    return str(url) if url else None


__all__ = ["unpaywall_pdf_for_doi"]
