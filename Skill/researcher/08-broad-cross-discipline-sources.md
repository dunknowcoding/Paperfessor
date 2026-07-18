# Skill: Broad, cross-disciplinary paper sources

**Agent**: Master's student
**When**: Surveying any topic — especially OUTSIDE computer science
(medicine, economics, social science, law, humanities, engineering).

## Source order (use the strongest available first)

1. **The cloud model's own paper search/read tool, if it has one.**
   When the configured provider/model exposes a built-in web or
   scholarly-search capability, prefer it first — it may reach
   full-text and paywalled venues the open APIs cannot. If the model
   has no such tool, or its coverage is thin for this field, fall
   through to the built-in sources below.

2. **OpenAlex** (built-in) — 200M+ works across EVERY discipline,
   free, no auth, with reconstructed abstracts. This is the primary
   cross-disciplinary source; it is not CS-specific.

3. **Crossref** (built-in) — 150M+ works, all fields; broad discovery
   for journals arXiv/OpenAlex miss (economics, medicine, law).

4. **arXiv** (built-in) — strong for CS / physics / quant-bio /
   econ preprints; weak elsewhere. Do not rely on it for non-STEM.

5. **Google Scholar via Playwright** (built-in) — broad recall,
   good for grey literature and citation chasing.

## Discipline / region notes

- **Medicine / life sciences**: OpenAlex + Crossref cover metadata;
  for free full text, PubMed Central / Europe PMC are the open
  archives. Prefer peer-reviewed journals over preprints for clinical
  claims.
- **Economics / finance**: journal articles (via OpenAlex/Crossref)
  and working-paper series (NBER, SSRN, RePEc) are the primary
  literature; weight top field journals.
- **Regional databases (e.g. CNKI for Chinese-language work)**: these
  usually require a subscription / login and cannot be fetched
  unattended. When a topic needs them, report that they require
  user-provided access rather than fabricating coverage.

## Judging venue tier (identify the TOP-tier venues)

A strong paper's reference list is long and drawn overwhelmingly from
TOP-tier conferences and journals. Prefer, and preferentially cite,
work from leading venues. To classify a venue's tier:

1. **OpenAlex source metadata** (built-in, robust): a source's
   `h_index`, 2-year mean citedness, and works count are strong tier
   signals. High h-index + high citedness = top-tier. Use
   `find_top_venues(field)` (OpenAlex works aggregation) to rank the
   venues actually publishing a field's work.
2. **Citation count of the paper itself**: within a field, heavily
   cited papers are usually in top venues — a usable prestige proxy
   when venue metadata is missing.
3. **Curated top-tier lists** (built-in `venue_index`): the community
   A*/A consensus for CS fields.
4. **External indices when accessible**: JCR quartile (Q1/Q2), CAS
   division, SCI/EI indexing, CORE rank, and journal databases such as
   LetPub (letpub.com) give impact factor / quartile / classification.
   These sites often need navigation or a login; when a topic needs a
   tier ruling they cannot resolve unattended, report which venues
   need a manual tier check rather than guessing.

Report each surveyed paper's venue and its tier signal so the PhD can
build a reference list that is long and dominated by top venues.

## Non-negotiable

Whatever the source, the same honesty rules apply: read what you can
actually access, extract only what the paper states, name the source
of every claim, and report inaccessible items plainly instead of
inventing their content.
