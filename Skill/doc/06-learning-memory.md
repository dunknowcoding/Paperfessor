# Skill: Durable learning memory (doc_learn)

**Agent**: PhD (only the PhD may touch this)
**When**: Every phase of the workflow.

`workspace/doc_learn.md` is your **durable** memory. Unlike `doc_memo.md`
and `article_memo.md` (per-run, cleared each paper), doc_learn is **never
cleared** — it accumulates distilled lessons across every run so the group's
experience compounds.

## What it holds

One concise line per lesson, grouped by category:
`- YYYY-MM-DD HH:MM | <conclusion>`

Suggested categories (add your own as needed):

- `venue-requirements` — page limits, appendix vs supplementary, format rules
  learned per venue and year (e.g. "NeurIPS 2026: 9-page main, appendix allowed").
- `coordination-ms` — what works / fails when tasking the master's student.
- `coordination-ug` — what works / fails when tasking the undergraduate.
- `paper-writing` — drafting, formatting, and rendering lessons (report vs
  conference paper vs journal paper).
- `method-design` — which method families won or failed, and why.
- `experiments` — data, protocol, and evaluation lessons.
- `process` — supervision and workflow lessons.

## The API (PhD-only)

- `learn(category, conclusion)` — record a short, self-contained lesson.
  Near-duplicates in a category are replaced; each category is capped so the
  memory stays compact.
- `recall_learnings(query=..., category=..., limit=...)` — search by category
  and/or word-overlap; consult it at the START of a phase.
- `forget_learning(category, contains=...)` — delete outdated lessons.

## How to use it every phase

1. **Plan** — `recall_learnings(query=direction)` before proposing a method;
   apply venue-requirement and method-design lessons.
2. **Survey / Code** — record coordination lessons when a worker report is
   thin, wrong, or slow.
3. **Write** — record venue-requirement lessons on venue pick; record
   writing/formatting lessons when a defect recurs.
4. **Finish** — record the method-design outcome (won/lost and why).

## Discipline

- Keep each line SHORT and self-contained — a future you must understand it
  with no other context.
- Prefer **updating/summarizing** an existing lesson over adding a near-copy.
- Delete lessons that are outdated or superseded (`forget_learning`).
- Never let a lesson leak local paths or private info — it is memory, not paper
  content, but keep it clean.
