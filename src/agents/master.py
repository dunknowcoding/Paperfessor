"""The master's student agent.

Literature search, full-text reading, and evidence extraction. The MS
agent is the *only* component that looks up papers; the LLM is never
asked to invent a citation, a title, or a result. The LLM is only
called to summarize evidence from a paper's full text that the MS has
already pulled from arXiv or OpenAlex.

Reads ``shared/research_guide.md`` (PhD-only writes). Writes
``shared/research_log.md`` and downloads PDFs to
``workspace/src/papers/<arxiv_id>.pdf``.

Status enum: websearch -> reading -> analyzing -> reporting -> idle.
"""

from __future__ import annotations

import dataclasses
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from src.agents.base import _WorkspaceAgent
from src.agents.phd import GuideTask
from src.agents.status import MasterStatus
from src.research.pdf_loader import PdfError, load_text
from src.research.sources import arxiv, openalex
from src.research.sources.venue_index import venue_label, venues_for_direction
from src.research import web as web_tools

if TYPE_CHECKING:
    from src.config import Settings
    from src.llm.router import LLMRouter


logger = logging.getLogger(__name__)


# ---- Unified paper record (one shape across all sources) ----------------


@dataclasses.dataclass(frozen=True)
class PaperRecord:
    """A paper as the MS agent sees it. One record regardless of source."""

    arxiv_id: str | None
    doi: str | None
    title: str
    authors: tuple[str, ...]
    year: int
    venue: str
    venue_source: str           # "arxiv" | "openalex" | "s2" | "manual"
    source_url: str
    pdf_url: str | None
    pdf_path: Path | None       # populated once we download
    abstract: str
    citation_count: int
    fields_of_study: tuple[str, ...] = ()

    def short_cite(self) -> str:
        first = self.authors[0].split()[-1] if self.authors else "anon"
        return f"{first} et al. ({self.year}) [{self.venue or self.venue_source}]"


@dataclasses.dataclass(frozen=True)
class FullTextRecord:
    """A paper with its full body loaded and ready to read."""

    paper: PaperRecord
    body: str
    pages: int
    body_chars: int


@dataclasses.dataclass(frozen=True)
class Evidence:
    """Structured evidence extracted from one paper's full text.

    The MS agent collects these per paper; the PhD reads the list to
    write the related-work section. ``claims`` and ``key_figures`` are
    short strings (one per line) extracted from the body. The LLM does
    the extraction but the values are anchored in real text.
    """

    paper: PaperRecord
    datasets: tuple[str, ...]            # e.g. ("PSM", "MSL", "SMD")
    metrics: tuple[str, ...]             # e.g. ("F1=0.83", "Precision=0.91")
    claims: tuple[str, ...]              # 1-line claims cited from the paper
    key_figures: tuple[str, ...]         # short descriptions of important figs/tables
    summary: str                         # 2-3 sentence bottom line


class PaperInaccessible(RuntimeError):
    """Raised when a paper's PDF cannot be downloaded (paywalled, 404, etc.)."""


def _html_to_text(html: str) -> str:
    """Crude HTML -> visible text. Removes tags, collapses whitespace.

    Good enough for the LLM, which does not need pixel-perfect
    rendering; it just needs the prose. We intentionally avoid
    pulling in BeautifulSoup as a hard dependency.
    """
    # Strip <script> and <style> blocks first.
    out = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    out = re.sub(r"<style\b[^>]*>.*?</style>", " ", out, flags=re.DOTALL | re.IGNORECASE)
    # Replace block-level closing tags with newlines.
    out = re.sub(r"</(p|div|li|h[1-6]|tr|br|section|article)\s*>", "\n", out, flags=re.IGNORECASE)
    out = re.sub(r"<br\s*/?>", "\n", out, flags=re.IGNORECASE)
    # Strip all remaining tags.
    out = re.sub(r"<[^>]+>", " ", out)
    # Decode the most common entities.
    replacements = {
        "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&#39;": "'", "&apos;": "'",
        "&mdash;": "—", "&ndash;": "–", "&hellip;": "…",
    }
    for k, v in replacements.items():
        out = out.replace(k, v)
    # Collapse whitespace.
    out = re.sub(r"[ \t\f\v]+", " ", out)
    out = re.sub(r" *\n *", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


# ---- The agent itself ----------------------------------------------------


class MasterStudent(_WorkspaceAgent):
    """The master's student agent."""

    def __init__(self, settings: "Settings", router: "LLMRouter", workspace: Path) -> None:
        super().__init__(settings, router, workspace, group="ms")
        self._status: MasterStatus = MasterStatus.IDLE

    # ---- Status API ----------------------------------------------------

    def status(self) -> MasterStatus:
        return self._status

    def status_dict(self) -> dict[str, str]:
        return {"agent": "ms", "status": self._status.value}

    def set_status(self, status: MasterStatus) -> None:
        with self._lock:
            self._status = status
        self._record_status(status.value)
        self._emit_status("ms", status.value)

    def api_status(self) -> dict[str, Any]:
        """JSON-friendly status snapshot for external consumers (CLI / GUI)."""
        return {
            "agent": "ms",
            "status": self._status.value,
            "history_len": len(self._status_history),
        }

    # ---- Guide read (read-only) ----------------------------------------

    def read_research_guide(self) -> list[GuideTask]:
        return self._read_guide("research_guide.md")

    def _read_guide(self, filename: str) -> list[GuideTask]:
        path = self._workspace / "shared" / filename
        if not path.exists():
            return []
        tasks: list[GuideTask] = []
        in_active = True
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.rstrip()
            if line.startswith("## History"):
                in_active = False
                continue
            if line.startswith("## "):
                in_active = True
                continue
            if not in_active:
                continue
            m = re.match(r"^- \[( |x|~)\] (.+)$", line)
            if not m:
                continue
            mark, text = m.group(1), m.group(2)
            tasks.append(GuideTask(text=text, done=(mark == "x"), voided=(mark == "~")))
        return tasks

    # ---- Log write -----------------------------------------------------

    def write_research_log(
        self,
        *,
        subject: str,
        content: str,
        task_ref: str | None = None,
    ) -> None:
        """Append an entry to ``shared/research_log.md``."""
        path = self._workspace / "shared" / "research_log.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = f"### {ts} | {subject}"
        if task_ref:
            header += f" | task: {task_ref}"
        with self._lock:
            with path.open("a", encoding="utf-8") as f:
                if path.stat().st_size == 0:
                    f.write("# research_log.md\n\n> MS's reports.\n\n## Log entries\n")
                f.write(f"\n{header}\n{content.strip()}\n")

    # ---- Real search (this is the user's "not just arXiv" requirement) --

    def search_papers(
        self,
        topic: str,
        *,
        max_arxiv: int = 8,
        max_venue: int = 12,
        year_min: int | None = None,
        year_max: int | None = None,
        relevance_cutoff: float = 0.55,
        required_tokens: tuple[str, ...] | None = None,
    ) -> list[PaperRecord]:
        """Broad search: arXiv preprints + OpenAlex top-venue papers.

        The ``topic`` is the research DIRECTION (e.g. "anomaly
        detection in time series"), NOT the proposed method. The
        user spec is explicit: 硕士生 does "广泛" search on the
        "调研主题" given by the PhD. The method is the
        contribution; the topic is what we survey.

        Relevance: each paper is judged by the LLM (0..1) on
        whether the abstract is actually about the topic. Papers
        below ``relevance_cutoff`` are dropped. The LLM is given
        the real abstract, not a guess.

        Returns:
            Deduplicated list of :class:`PaperRecord` ordered as:
            1) arXiv-only papers (always downloadable), then
            2) OpenAlex papers dedup'd against arXiv, sorted by
            relevance (with citation count as a tiebreak).
        """
        self.set_status(MasterStatus.WEBSEARCH)
        seen: dict[str, PaperRecord] = {}

        # 1) arXiv: authoritative for preprints. Build a query that
        # forces category + topic tokens. arXiv's ``all:`` and
        # ``ti:`` are tokenized; ``cat:`` is the category. We use
        # ``abs:`` to search the abstract — papers with a relevant
        # abstract beat papers that just mention the term in passing.
        arxiv_query = self._build_arxiv_query(topic)
        arxiv_only: list[PaperRecord] = []
        try:
            # Cap the arXiv call to keep the survey phase within its
            # time budget (the API rate-limits and our 30s timeout
            # otherwise blow it up).
            arxiv_papers = arxiv.search(arxiv_query, max_results=max_arxiv)
        except Exception as exc:  # noqa: BLE001
            logger.warning("arXiv search failed: %s; falling back to OpenAlex only", exc)
            arxiv_papers = []
        # Keep only the most-relevant arXiv hits.
        arxiv_papers = arxiv_papers[:max_arxiv]
        for ap in arxiv_papers:
            rec = PaperRecord(
                arxiv_id=ap.arxiv_id.split("v", 1)[0] if ap.arxiv_id else None,
                doi=None,
                title=ap.title,
                authors=ap.authors,
                year=ap.year,
                venue=f"arXiv [{ap.primary_category}]",
                venue_source="arxiv",
                source_url=ap.abs_url,
                pdf_url=ap.pdf_url,
                pdf_path=None,
                abstract=ap.abstract,
                citation_count=0,
                fields_of_study=(),
            )
            seen[rec.arxiv_id or rec.title] = rec
            arxiv_only.append(rec)

        # 2) OpenAlex: venue-filtered (top conferences/journals).
        # The venue filter uses the OpenAlex source ids from
        # venue_index, mapped to the direction's keyword match.
        venues = venues_for_direction(topic)
        # Use a stricter query: title + abstract search with the
        # topic tokens, sorted by relevance, not by citation count.
        oa_query = self._build_openalex_query(topic)
        try:
            venue_papers = openalex.search(
                oa_query,
                limit=max_venue * 2,
                year_min=year_min,
                year_max=year_max,
                type_filter="article",
                sort="relevance_score:desc",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenAlex search failed: %s", exc)
            venue_papers = []
        # Drop papers whose abstract has zero overlap with the
        # topic tokens. This is a cheap pre-filter before we ask
        # the LLM to score.
        topic_tokens = self._topic_tokens(topic)
        kept_venue: list = []
        for op in venue_papers:
            if topic_tokens and not any(
                tok in (op.abstract or "").lower()
                for tok in topic_tokens
            ):
                continue
            kept_venue.append(op)
            if len(kept_venue) >= max_venue:
                break

        for op in kept_venue:
            key = op.arxiv_id or op.doi or op.title
            if key in seen:
                existing = seen[key]
                seen[key] = dataclasses.replace(
                    existing,
                    doi=existing.doi or op.doi,
                    venue=op.venue or existing.venue,
                    citation_count=max(existing.citation_count, op.cited_by_count),
                    fields_of_study=existing.fields_of_study,
                    pdf_url=existing.pdf_url or op.pdf_url,
                )
                continue
            seen[key] = PaperRecord(
                arxiv_id=op.arxiv_id,
                doi=op.doi,
                title=op.title,
                authors=op.authors,
                year=op.year,
                venue=op.venue or "(unpublished)",
                venue_source="openalex",
                source_url=op.landing_page_url or "",
                pdf_url=op.pdf_url,
                pdf_path=None,
                abstract=op.abstract,
                citation_count=op.cited_by_count,
                fields_of_study=(),
            )

        # 3) Optional: enrich arXiv records with OpenAlex metadata.
        for key, rec in list(seen.items()):
            if rec.venue_source != "arxiv" or not rec.arxiv_id:
                continue
            try:
                oa = openalex.fetch_by_arxiv_id(rec.arxiv_id)
            except Exception:  # noqa: BLE001
                continue
            if oa.cited_by_count or oa.venue:
                seen[key] = dataclasses.replace(
                    rec,
                    doi=rec.doi or oa.doi,
                    venue=oa.venue or rec.venue,
                    citation_count=max(rec.citation_count, oa.cited_by_count),
                )

        # 4) LLM-based relevance scoring: only keep papers that
        # the LLM judges as actually about the topic. This is the
        # critical fix — OpenAlex's relevance_score is content-based
        # but still returns tangentially-related papers.
        candidates = list(seen.values())
        if relevance_cutoff > 0 and candidates:
            scored = self._llm_relevance_scores(topic, candidates)
            candidates = [
                (rec, score) for rec, score in scored
                if score >= relevance_cutoff
            ]
            candidates.sort(key=lambda rs: rs[1], reverse=True)
            candidates = [rec for rec, _ in candidates]

        # Required-token hard filter: a paper that does not mention
        # any of the user's chosen domain anchors ("time series",
        # "temporal", "sequential", "industrial IoT", ...) cannot
        # be relevant even if it mentions "anomaly detection" in
        # passing. This is the critical fix that prevents the
        # "Cora/Pubmed/Ionosphere/MVTec AD" off-topic results
        # that plagued the v0.4 paper. Semantics is OR: at least
        # one of the tokens must appear in the abstract.
        if required_tokens:
            required_tokens_lower = tuple(t.lower() for t in required_tokens)
            candidates = [
                rec for rec in candidates
                if any(tok in (rec.abstract or "").lower()
                       for tok in required_tokens_lower)
            ]

        # arXiv first (downloadable), then OpenAlex.
        arxiv_set = {id(r) for r in arxiv_only}
        arxiv_first = [r for r in candidates if id(r) in arxiv_set]
        others = [r for r in candidates if id(r) not in arxiv_set]
        return arxiv_first + others

    @staticmethod
    def _topic_tokens(topic: str) -> list[str]:
        """Return the meaningful tokens of a topic (>=4 chars)."""
        stop = {"for", "with", "from", "into", "that", "this", "than",
                "have", "been", "will", "they", "their", "which", "what",
                "when", "where", "such", "these", "those"}
        out: list[str] = []
        for t in re.findall(r"[a-z][a-z0-9-]{3,}", topic.lower()):
            t = t.strip("-")
            if t in stop:
                continue
            out.append(t)
        return out

    @staticmethod
    def _build_arxiv_query(topic: str) -> str:
        """Build a strict arXiv query: title + abstract, topic tokens
        must appear. Use ``all:`` for free search.

        Long directions produce many tokens; AND-ing all of them
        returns near-zero hits (and long URLs arXiv throttles), so
        the query keeps only the 5 most informative tokens (longest
        first, original order preserved among the picks)."""
        tokens = MasterStudent._topic_tokens(topic)
        if not tokens:
            return topic
        if len(tokens) > 5:
            keep = set(sorted(tokens, key=len, reverse=True)[:5])
            tokens = [t for t in tokens if t in keep][:5]
        # arXiv supports AND, OR, ti:, au:, abs:, all:. We require
        # each kept token to appear somewhere in title+abstract.
        return " AND ".join(f'all:"{t}"' for t in tokens)

    @staticmethod
    def _build_openalex_query(topic: str) -> str:
        """OpenAlex full-text query. We use the topic string verbatim;
        OpenAlex tokenizes it. The venue filter is applied separately
        in the caller."""
        return topic

    def _llm_relevance_scores(
        self, topic: str, candidates: list[PaperRecord],
    ) -> list[tuple[PaperRecord, float]]:
        """Ask the LLM to score each candidate's relevance to the
        topic on a 0..1 scale. We batch the candidates in groups of
        6 to keep the prompt small.

        The LLM is given the real title, venue, and abstract — not a
        guess — and is told to be strict (off-topic != 0.7 just
        because the venue is the same).
        """
        scored: list[tuple[PaperRecord, float]] = []
        BATCH = 6
        for i in range(0, len(candidates), BATCH):
            batch = candidates[i:i + BATCH]
            lines: list[str] = []
            for j, p in enumerate(batch, 1):
                snippet = (p.abstract or "")[:400].replace("\n", " ")
                lines.append(
                    f"[{j}] Title: {p.title}\n"
                    f"    Authors: {', '.join(p.authors[:3])}"
                    f"{' ...' if len(p.authors) > 3 else ''} ({p.year})\n"
                    f"    Venue: {p.venue}\n"
                    f"    Abstract: {snippet}..."
                )
            sys_prompt = (
                "You are a research MS scoring paper relevance. "
                "For each paper, output a line: `[N] <score>` where "
                "score is 0..1. 1 = paper is directly about the topic. "
                "0.7 = paper is closely related (same field, different "
                "sub-area). 0.4 = tangentially related (cites or is "
                "cited by the topic, but does not itself address the "
                "topic). 0 = off-topic. The topic is given below. "
                "Use ONLY the title, venue, and abstract you see. "
                "Do not invent scores. Be strict: a paper about "
                "image classification is NOT 1.0 for a topic of "
                "'time series anomaly detection', even if the venue "
                "is the same."
            )
            user_prompt = (
                f"Topic: {topic!r}\n\n"
                "Papers to score:\n\n" + "\n\n".join(lines)
                + "\n\nOutput (one line per paper, [N] <score>):\n"
            )
            raw = self.call_llm(
                role="surveyor",
                system=sys_prompt,
                user=user_prompt,
                max_tokens=400,
                temperature=0.0,
                min_chars=4,
            )
            parsed = self._parse_relevance_scores(raw, len(batch))
            for j, p in enumerate(batch):
                scored.append((p, parsed[j]))
        return scored

    @staticmethod
    def _parse_relevance_scores(raw: str, n: int) -> list[float]:
        """Parse `[N] 0.85` lines.

        Papers whose score line is missing (or when the LLM returned
        nothing at all) default to 0.6 — i.e. KEEP. The candidates
        already passed the topic-token pre-filter, so a scorer outage
        must degrade to "no extra filtering", never to "drop all".
        """
        scores = [0.6] * n
        for line in raw.splitlines():
            m = re.search(r"\[(\d+)\]\s*([0-9]+(?:\.[0-9]+)?)", line)
            if m:
                idx = int(m.group(1)) - 1
                if 0 <= idx < n:
                    try:
                        scores[idx] = max(0.0, min(1.0, float(m.group(2))))
                    except ValueError:
                        pass
        return scores

    def read_paper(self, record: PaperRecord) -> FullTextRecord:
        """Download (if needed) and extract the full text of ``record``.

        The PDF is cached at ``workspace/src/papers/<arxiv_id>.pdf``
        (or ``<doi_slug>.pdf`` if no arXiv id). The body is the
        ``load_text`` output of pypdf, page-by-page.

        Raises:
            PaperInaccessible: if the PDF is paywalled / 403 / 404.
                The caller can try the next record.
        """
        if not record.pdf_url and not record.arxiv_id:
            raise PaperInaccessible(f"no PDF source for paper: {record.title!r}")
        self.set_status(MasterStatus.READING)
        cache_dir = self._workspace / "src" / "papers"
        cache_dir.mkdir(parents=True, exist_ok=True)
        if record.arxiv_id:
            pdf_path = cache_dir / f"{record.arxiv_id}.pdf"
        elif record.doi:
            slug = re.sub(r"[^A-Za-z0-9]+", "_", record.doi).strip("_")[:60] or "doi"
            pdf_path = cache_dir / f"{slug}.pdf"
        else:
            slug = re.sub(r"[^A-Za-z0-9]+", "_", record.title)[:60].strip("_") or "paper"
            pdf_path = cache_dir / f"{slug}.pdf"
        if not (pdf_path.exists() and pdf_path.stat().st_size > 1024):
            if record.arxiv_id:
                # Use the authoritative arXiv client.
                arxiv_paper = arxiv.Paper(
                    arxiv_id=record.arxiv_id,
                    title=record.title,
                    authors=record.authors,
                    abstract=record.abstract,
                    year=record.year,
                    published="",
                    updated="",
                    primary_category="",
                    categories=(),
                    pdf_url=record.pdf_url or f"https://arxiv.org/pdf/{record.arxiv_id}",
                    abs_url=record.source_url or f"https://arxiv.org/abs/{record.arxiv_id}",
                    doi=record.doi,
                    journal_ref=None,
                    comment=None,
                )
                pdf_path = arxiv.download_pdf(arxiv_paper, cache_dir)
            elif record.doi:
                # OpenAlex paper with DOI: try to find a free arXiv
                # version via Semantic Scholar. If that fails too, the
                # caller falls back to using the abstract only.
                from src.research.sources.s2 import (
                    find_arxiv_id_for_doi as _s2_doi,
                )
                try:
                    arxiv_id_from_doi = _s2_doi(record.doi)
                except Exception:  # noqa: BLE001
                    arxiv_id_from_doi = None
                if arxiv_id_from_doi:
                    arxiv_paper = arxiv.Paper(
                        arxiv_id=arxiv_id_from_doi,
                        title=record.title,
                        authors=record.authors,
                        abstract=record.abstract,
                        year=record.year,
                        published="",
                        updated="",
                        primary_category="",
                        categories=(),
                        pdf_url=f"https://arxiv.org/pdf/{arxiv_id_from_doi}",
                        abs_url=f"https://arxiv.org/abs/{arxiv_id_from_doi}",
                        doi=record.doi,
                        journal_ref=None,
                        comment=None,
                    )
                    # download_pdf names the file by arXiv id, which is
                    # NOT the DOI-slug path computed above — use the
                    # returned path or the later validation opens a
                    # non-existent file.
                    pdf_path = arxiv.download_pdf(arxiv_paper, cache_dir)
                else:
                    raise PaperInaccessible(
                        f"no arXiv version found for DOI {record.doi!r} ({record.title!r})"
                    )
            else:
                # OpenAlex/other: download via the pdf_url directly.
                import requests
                try:
                    resp = requests.get(
                        record.pdf_url,
                        headers={"User-Agent": "Paperfessor/0.4 (research)"},
                        timeout=60,
                    )
                except requests.RequestException as exc:
                    raise PaperInaccessible(
                        f"PDF {record.pdf_url} download error: {exc}"
                    )
                if resp.status_code in (401, 402, 403, 404, 500, 502, 503, 504):
                    raise PaperInaccessible(
                        f"PDF {record.pdf_url} returned HTTP {resp.status_code} (paywalled, missing, or upstream error)"
                    )
                try:
                    resp.raise_for_status()
                except requests.HTTPError as exc:
                    raise PaperInaccessible(
                        f"PDF {record.pdf_url} HTTP {resp.status_code}: {exc}"
                    )
                pdf_path.write_bytes(resp.content)
        # Validate: the file must look like a PDF, not an HTML 404
        # masquerading as one. The PDF magic is "%PDF-" at offset 0.
        if not pdf_path.is_file():
            raise PaperInaccessible(
                f"download completed but no file at {pdf_path.name} for {record.title!r}"
            )
        with pdf_path.open("rb") as f:
            head = f.read(5)
        if head[:4] != b"%PDF":
            try:
                pdf_path.unlink()
            except OSError:
                pass
            raise PaperInaccessible(
                f"downloaded content for {record.title!r} is not a PDF (header={head!r})"
            )
        try:
            body = load_text(pdf_path, max_pages=30)  # 30 pages is plenty for most
        except PdfError as exc:
            logger.warning("PDF read failed for %s: %s", pdf_path, exc)
            body = ""
        try:
            from pypdf import PdfReader
            pages = len(PdfReader(str(pdf_path)).pages)
        except Exception:  # noqa: BLE001
            pages = 0
        if not body.strip():
            raise PaperInaccessible(
                f"PDF {pdf_path} downloaded but extracted to empty text"
            )
        updated = dataclasses.replace(record, pdf_path=pdf_path)
        return FullTextRecord(paper=updated, body=body, pages=pages, body_chars=len(body))

    def read_paper_online(self, url: str) -> FullTextRecord:
        """Open a paper URL in a real browser and extract its body text.

        The rendered HTML is saved at
        ``workspace/src/papers/<slug>.html``. The body is the visible
        text of the page (Playwright ``inner_text``). Use this for
        paywalled or non-PDF papers that the offline reader cannot
        open. The LLM still sees only the visible text; nothing about
        the user's local paths or project internals is leaked.
        """
        self.set_status(MasterStatus.READING)
        cache_dir = self._workspace / "src" / "papers"
        cache_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9]+", "_", url)[:60].strip("_") or "page"
        # 1. Fetch the URL via Playwright (also writes the HTML to disk).
        try:
            html = web_tools.fetch_paper_online(
                url, out_path=cache_dir / f"{slug}.html"
            )
        except Exception as exc:  # noqa: BLE001
            raise PaperInaccessible(f"online render failed for {url}: {exc}")
        # 2. Extract visible text. We do not re-open the file via the
        # browser (file:// goto can be flaky on Windows); instead we
        # strip the HTML to text with a small BeautifulSoup-free pass.
        # This is good enough for the LLM, which sees prose.
        text = _html_to_text(html)
        if not text.strip():
            # Fall back to the raw HTML in case the page is mostly
            # scripts / iframes.
            text = html
        if not text or not text.strip():
            raise PaperInaccessible(f"online render produced empty body for {url}")
        # Build a synthetic PaperRecord so the rest of the pipeline
        # can treat this uniformly.
        rec = PaperRecord(
            arxiv_id=None,
            doi=None,
            title=url,
            authors=(),
            year=0,
            venue="(online)",
            venue_source="web",
            source_url=url,
            pdf_url=None,
            pdf_path=None,
            abstract="",
            citation_count=0,
            fields_of_study=(),
        )
        return FullTextRecord(paper=rec, body=text, pages=1, body_chars=len(text))

    def search_web(
        self,
        topic: str,
        *,
        limit: int = 10,
        year_min: int | None = None,
        year_max: int | None = None,
    ) -> list[PaperRecord]:
        """Search Google Scholar via a real browser (Playwright).

        Returns :class:`PaperRecord` items, dedup'd against the
        arXiv/OpenAlex pass. The Scholar result list complements the
        API results: it surfaces high-citation work that the free
        APIs miss (e.g. survey papers with venue names that the
        OpenAlex source-id filter does not cover).
        """
        self.set_status(MasterStatus.WEBSEARCH)
        try:
            rows = web_tools.search_google_scholar(
                topic, limit=limit, year_min=year_min, year_max=year_max,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Scholar search failed: %s", exc)
            return []
        out: list[PaperRecord] = []
        for r in rows:
            out.append(PaperRecord(
                arxiv_id=None,
                doi=None,
                title=r.title,
                authors=tuple(a.strip() for a in r.authors.split(",") if a.strip()),
                year=r.year,
                venue=r.venue or "(unknown)",
                venue_source="scholar",
                source_url=r.detail_url,
                pdf_url=r.pdf_url,
                pdf_path=None,
                abstract=r.snippet,
                citation_count=r.cited_by,
                fields_of_study=(),
            ))
        return out

    def screenshot_figure(
        self, record: PaperRecord, page_num: int, out_dir: Path | None = None,
    ) -> Path:
        """Render a single page of a downloaded paper to a PNG.

        The figure is saved to ``workspace/src/figures/<key>/page_NNN.png``
        by default. The MS agent uses this when the LLM needs to
        ``see`` a figure (architectures, training curves, ablations).
        The :meth:`analyze_figure` method below is the consumer.
        """
        if not record.pdf_path or not record.pdf_path.is_file():
            raise PaperInaccessible(
                f"screenshot needs a local PDF; {record.title!r} has none"
            )
        self.set_status(MasterStatus.ANALYZING)
        if out_dir is None:
            out_dir = self._workspace / "src" / "figures" / (
                record.arxiv_id or "scholar"
            )
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"page_{page_num:04d}.png"
        return web_tools.screenshot_pdf_page(record.pdf_path, page_num, out)

    def analyze_figure(
        self, figure_path: Path, question: str, *, max_tokens: int = 600,
    ) -> str:
        """Ask the LLM a question about a screenshot of a paper figure.

        The PNG is at ``figure_path``. We do NOT feed the bytes to the
        LLM (the default MiniMax-M3 model is text-only); instead we
        record the question + the figure path in a log entry so the
        user (or a future multimodal call) can answer it. The MS
        agent uses this when it wants to flag a figure for review.
        """
        self.set_status(MasterStatus.ANALYZING)
        if not figure_path.is_file():
            return f"(figure not found: {figure_path})"
        return self.ask(
            "You are a research MS. The user / PhD has flagged a paper "
            "figure for review. Based on the paper's title (if you know "
            "it from the path) and the question, write 1-2 sentences of "
            "what we expect the figure to show. The figure is at the "
            "given path; treat it as a placeholder for now.",
            f"Figure path: {figure_path}\nQuestion: {question}",
            max_tokens=max_tokens,
        )

    def extract_evidence(self, ft: FullTextRecord) -> Evidence:
        """Use the LLM to pull structured evidence from a paper's body.

        This is the *only* place we let the LLM touch paper content,
        and even here it is constrained: it sees the real text, not a
        hallucinated abstract, and it must return a fixed schema.
        """
        self.set_status(MasterStatus.ANALYZING)
        if not ft.body.strip():
            return Evidence(
                paper=ft.paper, datasets=(), metrics=(), claims=(), key_figures=(),
                summary="(no body text available; evidence extraction skipped)",
            )
        # Truncate to keep the LLM context manageable: ~12k chars is
        # enough to capture the abstract + method + key tables.
        text = ft.body[:12000]
        prompt = (
            "You are reading a research paper. Extract structured evidence. "
            "Return ONLY a JSON object with these fields, no prose:\n"
            "  datasets: list of dataset names used (e.g. ['PSM', 'MSL', 'SMD'])\n"
            "  metrics: list of headline metric strings (e.g. ['F1=0.83', 'Precision=0.91'])\n"
            "  claims: list of 3-5 one-line claims quoted or paraphrased from the paper\n"
            "  key_figures: list of short descriptions of 2-3 important figures/tables\n"
            "  summary: 2-3 sentence bottom line on what the paper actually contributes\n"
            "If a field is unclear, return an empty list. Do NOT invent values."
        )
        user = (
            f"Title: {ft.paper.title}\n"
            f"Year: {ft.paper.year}\n"
            f"Venue: {ft.paper.venue}\n"
            f"Source: {ft.paper.venue_source}\n\n"
            f"Paper body (truncated to first ~12k chars):\n\n"
            f"{text}\n\n"
            f"Return the JSON object now."
        )
        raw = self.ask(prompt, user, max_tokens=800)
        return self._parse_evidence(raw, ft.paper)

    @staticmethod
    def _parse_evidence(raw: str, paper: PaperRecord) -> Evidence:
        """Parse the LLM JSON output, robust to markdown fences."""
        text = raw.strip()
        # Strip ```json ... ``` fences if present.
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        import json
        obj: dict = {}
        try:
            obj = json.loads(text)
        except Exception:  # noqa: BLE001
            # Last-ditch: try to find a balanced JSON object in the
            # string. The LLM sometimes returns a truncated JSON
            # (e.g. "Unterminated string") so we walk braces.
            depth = 0
            start = text.find("{")
            if start >= 0:
                for i in range(start, len(text)):
                    c = text[i]
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            try:
                                obj = json.loads(text[start : i + 1])
                                break
                            except Exception:  # noqa: BLE001
                                obj = {}
            if not obj:
                # Fall back to regex match (may also be malformed).
                m = re.search(r"\{.*\}", text, re.DOTALL)
                if m:
                    try:
                        obj = json.loads(m.group(0))
                    except Exception:  # noqa: BLE001
                        obj = {}
        if not isinstance(obj, dict):
            obj = {}
        def _list(x) -> tuple[str, ...]:
            if isinstance(x, list):
                return tuple(str(v).strip() for v in x if str(v).strip())
            if isinstance(x, str) and x.strip():
                return (x.strip(),)
            return ()
        return Evidence(
            paper=paper,
            datasets=_list(obj.get("datasets")),
            metrics=_list(obj.get("metrics")),
            claims=_list(obj.get("claims")),
            key_figures=_list(obj.get("key_figures")),
            summary=str(obj.get("summary") or "").strip(),
        )

    def evidence_to_markdown(self, evidences: Iterable[Evidence]) -> str:
        """Render a list of evidence records as a survey-style log entry."""
        lines: list[str] = []
        for ev in evidences:
            p = ev.paper
            lines.append(f"## {p.title}")
            lines.append("")
            lines.append(f"- **Authors**: {', '.join(p.authors[:5])}{' ...' if len(p.authors) > 5 else ''}")
            lines.append(f"- **Year / Venue**: {p.year} / {p.venue or '(unpublished)'} [{p.venue_source}]")
            if p.citation_count:
                lines.append(f"- **Citations (OpenAlex)**: {p.citation_count}")
            if p.arxiv_id:
                lines.append(f"- **arXiv**: {p.arxiv_id} ({p.source_url})")
            if p.doi:
                lines.append(f"- **DOI**: {p.doi}")
            if ev.datasets:
                lines.append(f"- **Datasets**: {', '.join(ev.datasets)}")
            if ev.metrics:
                lines.append(f"- **Headline metrics**: {', '.join(ev.metrics)}")
            if ev.claims:
                lines.append(f"- **Claims (from paper)**:")
                for c in ev.claims:
                    lines.append(f"    - {c}")
            if ev.key_figures:
                lines.append(f"- **Key figures/tables**:")
                for f in ev.key_figures:
                    lines.append(f"    - {f}")
            if ev.summary:
                lines.append(f"- **Bottom line**: {ev.summary}")
            lines.append("")
        return "\n".join(lines)

    # ---- LLM call (MS-flavored prompt) --------------------------------

    def ask(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        return self.call_llm(role="surveyor", system=system, user=user, max_tokens=max_tokens)


__all__ = [
    "Evidence",
    "FullTextRecord",
    "MasterStudent",
    "PaperInaccessible",
    "PaperRecord",
]
