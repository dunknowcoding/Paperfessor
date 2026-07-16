# Skill: Always check the archive first

**Agent**: PhD
**When**: Designing a new method, or before starting a new run.

`workspace/archived/` is the project's permanent record of every
prior attempt. Before you invest in a new method:

1. **List** `workspace/archived/` and read each `metadata.yaml`.
2. **For each `success: true`** — note the method. Do not propose
   the same method again unless the user explicitly wants a
   re-run.
3. **For each `success: false`** — read the `reason` field. If
   the reason is "theory was wrong" or "model is broken," do
   not propose the same method even with new hyperparameters —
   the underlying issue is the method, not the search.
4. **If you do propose a method that resembles a prior failure** —
   explain explicitly in `doc_memo.md` why you think this run
   will be different. The MS and UG will read the memo.

A method that has already been tried, succeeded, or documented-
as-failed is not a candidate. The archive is your first stop.

## SQLite-backed lookup (use this before listing the folder)

The PhD's `lookup_method(area, method)` returns the most recent
archived row for a given (area, method). Use it as a cheap
pre-filter before walking `workspace/archived/`. The DB has the
same fields as the YAML; the YAML is the human-readable form,
the DB is the fast form.

## Veto reasons that are non-recoverable

If the archive's `reason` is one of:
- "theory was wrong" / "theoretical flaw"
- "model architecture is broken" / "representation collapse"
- "experiment is not feasible" / "no public dataset"

then the same method is **vetoed** for this direction. A new
attempt must change the method, not the hyperparameters.
