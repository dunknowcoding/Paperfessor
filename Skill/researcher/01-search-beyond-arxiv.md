# Skill: Search beyond arXiv

**Agent**: Master's student
**When**: The PhD gives you a research theme.

The user's spec is explicit: **do not only search arXiv**. The
PhD's spec (req.txt) demands "perform broad full-text search,
not only arXiv; use top conferences/journals in related fields
as the primary theoretical reference, and other tiers as
auxiliary references". You must cover:

1. **Top venue proceedings** — NeurIPS, ICML, ICLR, AAAI, ACL,
   EMNLP, CVPR, ICCV, ECCV, KDD, ICDM, WWW, etc. Look at the
   last 3 years of accepted papers.
2. **Top journals** — JMLR, TPAMI, IJCV, TACL, Nature Machine
   Intelligence, etc. These are slower but more rigorous.
3. **arXiv** — recent preprints from strong groups; NOT the
   default. arXiv is a venue, not a substitute for reading the
   conference version.
4. **OpenReview** — accepted papers with public reviews, which
   give you the community's take on the work.
5. **Semantic Scholar / Google Scholar** — citation graphs and
   "cited by" traversal to find newer work that cites the
   original.

## How to actually do this in Paperfessor

You have three real search paths. Use **all three** in this
order; dedup by title.

1. **arXiv API** (`src/research/sources/arxiv.py`): the
   authoritative source for arXiv preprints. Free, no auth.
   `arxiv.search(query, max_results=5, categories=[...])`.

2. **OpenAlex API** (`src/research/sources/openalex.py`): cross-
   venue metadata, abstracts (reconstructed from the inverted
   index), citation counts, venue names, OA PDFs. Free, no auth.
   Use the venue filter from `venue_index.venues_for_direction(...)`
   so the search stays on-topic.

3. **Google Scholar via Playwright**
   (`paperfessor/research/web.py:search_google_scholar`): the only
   path that covers non-arXiv/non-OpenAlex papers (publisher
   paywalls, lab sites, OpenReview, etc.). Slow, but high
   recall. **Always include in the search**, even if it
   returns 0 results — the PhD will downgrade a survey that
   skipped Scholar.

## Getting the FULL TEXT (the open-access ladder)

A found paper is worthless until you can read it. `read_paper`
climbs this ladder automatically — know it so you can explain
your inaccessible list:

1. **arXiv PDF** — always downloadable when an arXiv version
   exists (also resolved from a DOI via Semantic Scholar).
2. **Semantic Scholar `openAccessPdf`** — legal OA copies hosted
   by publishers, PubMed Central, and institutional repositories.
3. **Unpaywall** — the OA index keyed by DOI. Only queried when
   the user configured `PAPERFESSOR_CONTACT_EMAIL` (its terms
   require a real address).
4. **Playwright-rendered HTML** — many OA papers publish full
   text as HTML; the landing page is rendered in a real browser
   and the visible text is used when it is substantial (> 4000
   chars).

Only when EVERY rung fails may a paper be logged as
inaccessible — and the log entry must say which rungs were tried.

## When you log a survey

- Name the venues and the queries.
- For each paper, log: title, authors, year, venue, abstract,
  datasets, headline metric, PDF URL, why it matters.
- Mark paywalled / 404 papers explicitly. The PhD expects a
  "inaccessible" list, not a silent drop.
- If you only found 3 papers, say so. The PhD will then decide
  whether to widen the search or accept the thin corpus.

The PhD will downgrade surveys that lean too hard on arXiv.
