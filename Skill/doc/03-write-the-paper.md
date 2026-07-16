# Skill: Write a top-venue paper

**Agent**: PhD
**When**: All experiments are done, you're writing the paper.

A top-venue paper is not a long paper — it is a **dense** paper.
Every sentence must be evidence-anchored; every claim cites a
real paper from the survey.

## 1. Pick the venue template first

Use `phd.detect_and_fetch_venue(direction)`. The PhD's LLM picks
the single best target venue for the direction (KDD for data
mining / time series; CVPR for vision; ACL for NLP; NeurIPS for
general ML; etc.). The PhD then downloads the venue's official
template and falls back to `acmart [sigconf]` if the download
fails. **The user override in the direction string wins** —
if the user writes "submit to NeurIPS", the PhD uses NeurIPS.

If LaTeX is not installed at all, fall back to `pandoc paper.md
-o paper.docx` (Office) or just keep the `.md` and say so in
`article_memo.md`'s `Template check` field.

## 2. Page budget (CRITICAL)

- **Main body must be ≤ venue's page limit** (NeurIPS / ICML / ICLR
  / KDD = 9; ACL / EMNLP / CVPR / ICCV / ICRA / IROS = 8; AAAI /
  IJCAI = 7). acmart does not enforce this; the PhD must count
  the rendered PDF pages and split.
- **Anything that pushes over the page limit** goes to
  `paper_appendix.md` and renders as `\appendix` in the .tex.
  This includes:
  - Extended proofs / theory derivations
  - Extra experiments / ablations
  - Hyperparameter tables
  - Per-dataset detail
  - Dataset statistics
- **The appendix must not contain**:
  - `src/` file names (e.g. `workspace/src/code/train.py` is FORBIDDEN)
  - Local PC paths (e.g. `G:\Arduino\...`, `/Users/...`, `C:\...`)
  - Project-internal names (skill files, doc_memo references, etc.)
  - Anything not in the public paper domain

The PhD's `paper_appendix.md` writer MUST redactor-check the
content before it lands in the .tex.

## 3. Figure design and sizing

The venue template fixes the geometry: a two-column acmart page
has a **column width of ~3.33 in (240 pt)** and a **text width of
~7 in (504 pt)**. Every figure must be designed FOR the slot it
will occupy — never scaled down until unreadable.

- **Column-span judgement**: aspect ratio (w/h) >= 1.8, or any
  figure with more than ~4 panels or 6 bar groups, spans both
  columns (`figure*`, width <= 0.85\textwidth). Compact plots
  (single panel, tall) stay single-column (`figure`, width
  0.9\linewidth).
- **Text inside a figure must render at >= 7 pt after scaling.**
  Rule of thumb: generate single-column PNGs at ~3.3 in wide with
  8 pt fonts, double-column at ~7 in wide with 8-9 pt fonts, both
  at >= 200 dpi. If labels would shrink below 7 pt, the figure is
  too dense — split it or span both columns.
- At least **4 figures** in the main body, each cited via
  `\ref{fig:...}`. The Reviewer will reject a paper with 0 figures.
- Side-by-side: two `\subfloat` blocks. Stacked: one `\subfloat`
  with multiple subfigures.
- Every figure needs a caption that states what the reader should
  SEE ("CCIAS beats kNN on 2 of 3 datasets"), a label, and a data
  source. No floating screenshots, no internal names/hashes in
  titles or captions.
- The MS's `screenshot_figure` or UG's `screenshot` produces the
  PNG; the PhD copies it into `paper/figures/`.

## 4. Table design

- At least one **main-results table** (Table 1) with k-seed
  error bars. No single-seed numbers in the main body.
- **Design for the slot**: <= 4 columns fits a single column
  (`table`); 5+ columns spans both (`table*`). If a table would
  need `\resizebox` below ~85% scale to fit, it has too many
  columns — move columns out instead of shrinking:
  - Split metrics across two tables (F1/Precision/Recall vs
    AUROC/AUPRC), or
  - Put datasets in row groups and metrics in columns, or
  - Move the long tail to the Appendix.
- Numbers: 3 significant decimals, `mean ± half-CI`, best result
  per dataset in **bold**. Left-align text columns, right-align
  numeric ones.
- Table 1 compares the proposed method against every baseline on
  every evaluated dataset, with a "Source" column marking
  `reproduced` vs `cited`. Never mix reproduced and cited numbers
  in one column without the marker.
- Captions go ABOVE tables (ACM style) and must say what the
  table shows and under which protocol.
- Per-dataset detail tables go in the **Appendix** (page budget).

## 5. Write like a PUBLISHED paper — kill everything else

Model the prose on published top-venue papers in the field (e.g.
the Anomaly Transformer paper at ICLR '22, USAD at KDD '20):
abstract states the problem, the method, and the MEASURED headline
number; introduction ends in a 3-bullet contribution list; every
factual claim carries an author-year citation; results are
analyzed (where the method wins, where it loses, and why), not
just tabulated.

Forbidden — AI/process phrasing:

- "It is worth noting that…" / "In recent years…" / "Many researchers have…"
- "This is an exciting area…" / "Extensive experiments demonstrate…"
- "The rest of the paper is organized as follows." (boilerplate)
- Process/handoff sections: "What changed", "Evidence",
  "Remaining risks", "Next steps" — these belong in the work LOGS,
  never in the paper.
- Any mention of the agents or workflow: "PhD", "MS", "UG",
  "master's student", "undergraduate", "supervisor", "agent",
  "Paperfessor". Published papers say "we".
- Invented BibTeX keys like `[xu2018unsupervised]` — cite
  author-year (Wu et al., 2024) mapping to the References list.
- Promises of future numbers ("to be reported") when measured
  numbers exist — put the real numbers in.

Required:
- Active voice, declarative
- Every claim cites a paper from the survey (author-year)
- "We show X (Sec. N) achieves Y on Z (Table 1) at P % 95-CI."
- References list of at least ~18 real, verifiable entries

If the LLM produces AI-style filler, **revise at the source** —
do not paper over with a regex. The MS has a `style review` skill
that calls this out.

## 6. Preview every page

After every section draft:
1. Compile the .tex → .pdf.
2. Render the new pages with `pypdfium2` (use the
   `screenshot_pdf_page` helper in `src/research/web.py`).
3. Run the Article 19 layout checks (font size, line spacing,
   paragraph spacing, no overlap, density, no margin crossing).
4. Append a `visual_inspect` row to `article_memo.md` with
   pass/fail for each check.
5. If any check fails, **revise the section** and re-preview.
   Do not move to the next section until this one is clean.

## 7. Datasets & experimental environment

If the paper has experiments, the Experimental Setup section
must describe, in this order:
- **Hardware** (CPU/GPU, RAM)
- **Software** (Python, PyTorch / TensorFlow, key libraries + versions)
- **Datasets** (name, source URL, license, sample count, feature count,
  train/val/test split ratio)
- **Protocol** (k seeds, batch size, optimizer, lr, schedule,
  early-stopping rule, evaluation metric)
- **Baselines** (with citations)

This is the spec; do not skip hardware or software.

## 8. Style / honesty / no project-internal info

- No local paths in the paper (e.g. `G:\Arduino\driver\Paperfessor\...`).
- No `Skill/` content quoted in the paper.
- No `doc_memo.md` / `article_memo.md` references in the paper.
- No fake authors. The author block is "Paperfessor Agent Group"
  unless the user has supplied real authors.
- No fake datasets. Datasets in the paper are the ones the UG
  actually ran on.
- No fake numbers. If an experiment has not been run, the paper
  says plainly that the result is pending — with no placeholder
  cells and no internal role names. Prefer running the experiment
  before writing the section.

The PhD runs the redactor pass before compile. The check is
literal: a `\G:` or `\Users` or `workspace/` in the .tex fails
the build.
