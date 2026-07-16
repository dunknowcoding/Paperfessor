# Skill: Investigate venue submission requirements

**Agent**: MS
**When**: The PhD names a target venue (or asks which venue fits the
direction). This is broader investigation than paper search — the
sources are the venue's OFFICIAL pages, not articles.

## What to fetch

Use `read_paper_online` / `search_web` on the venue's official
call-for-papers and author-kit pages (e.g. `kdd.org` CFP,
`neurips.cc` Call, ACL's author guidelines, the ACM/IEEE template
provider pages). Collect, verbatim where possible:

1. **Template + class**: which LaTeX class and options are mandated
   (e.g. `acmart sigconf`, `neurips_2026.sty`, `acl.sty`), and where
   the official template lives.
2. **Page limits**: main body limit, whether references count,
   appendix policy.
3. **Anonymization**: double-blind or not; what must be redacted
   (author names, acknowledgments, self-citations phrasing, links to
   personal repos).
4. **Figures/tables rules**: color usage, minimum font in figures,
   caption position, placement rules.
5. **Reference style**: numeric vs author-year, mandated bib style.
6. **Extra artifacts**: checklist (NeurIPS), ethics statement,
   reproducibility statement, supplementary size limits.
7. **Deadlines and submission site** (for the report only; do not
   act on them).

## How to report

Write one `research_log.md` entry titled
`Venue requirements: <venue>` with a checklist the PhD can apply
mechanically — one line per rule, each marked `[hard]` (submission
fails without it) or `[soft]` (style expectation). Quote exact
numbers ("9 pages excluding references"), never paraphrase a limit
from memory. If a page could not be fetched, say so explicitly —
the PhD must know which rules are unverified.

## Rules

- Official sources only (venue domain, template provider). A blog
  post summarizing the CFP is supporting evidence, not authority.
- Record the URL of every rule so the PhD can verify.
- If the venue is unspecified, investigate the top venue for the
  direction and one fallback venue.
